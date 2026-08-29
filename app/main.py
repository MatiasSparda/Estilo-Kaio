import customtkinter as ctk
from tkinter import filedialog, messagebox, simpledialog
import json
import os
import sys
import uuid
import threading
from .region_selector import RegionSelector
from .screen_capture import ScreenCaptureManager
from .translator import (
    Translator,
    TranslatorOverlay,
    TranslatorOverlayOver,
    TRANSLATOR_LANGUAGES,
    TRANSLATION_PROVIDERS,
    TRANSLATION_PROVIDER_ETA,
    normalize_translation_provider,
)
from .ollama_assistant import (
    GuideAssistant,
    AssistantResponseWindow,
    ASSISTANT_LANGUAGES,
    is_progress_query,
)
from .gemma_translate import (
    BACKEND_LABELS,
    DEFAULT_MODEL,
    LiteRTManager,
    get_preferred_backend,
    is_server_running as gemma_is_running,
    resolve_model_id,
    set_preferred_backend,
    translate_query_keywords,
    write_litert_config,
)
from .guide_parser import (
    parse_guide_sections,
    build_context_for_section,
    build_progress_context,
    build_progress_candidate_contexts,
    filter_sections_by_query,
    is_long_guide,
    resolve_auto_section_id,
)
from . import ui_theme as theme


def repo_root() -> str:
    """Raíz del repo (config.json / guias). En exe frozen = carpeta del exe."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def app_base_dir() -> str:
    return repo_root()


CONFIG_FILE = os.path.join(repo_root(), "config.json")


def resolve_config_path() -> str:
    """Prefiere config en la raíz del repo; migra desde cwd si hace falta."""
    primary = CONFIG_FILE
    candidates = [primary, os.path.join(os.getcwd(), "config.json")]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return primary


SECTION_AUTO = "Auto (según mi pregunta)"
SECTION_FULL = "Toda la guía (no recomendado)"


def default_session(name="Sesión principal"):
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "translator_source": "en",
        "translator_target": "es",
        "assistant_language": "es",
        "guide_path": "",
        "translator_region": None,
        "journal_region": None,
        "overlay_mode": "layer",  # layer | over — por perfil/juego
        "ocr_engine": "oneocr",  # oneocr | easyocr | winrt
    }


class EstiloKaioApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Estilo Kaio")
        self.minsize(780, 700)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=theme.BG)

        self.sessions = []
        self.active_session_id = None
        self.guide_text = ""
        self.guide_sections = []
        self.translate_hotkey = "alt+t"
        self.assistant_hotkey = "alt+g"
        self.stop_overlay_hotkey = "alt+x"
        self.overlay_position = None  # {"x": int, "y": int} — posición Layer (global)
        self.window_geometry = "900x820"
        self.response_geometry = "780x720"
        self.auto_start_gemma = False
        self.gemma_backend = "cpu"
        self.default_ocr_engine = "oneocr"
        self.translation_provider = "argos"  # argos | argos_gemma | gemma

        self.capture_manager = ScreenCaptureManager(self)
        self.translator = Translator()
        self.guide_assistant = GuideAssistant()
        self.litert_manager = LiteRTManager()

        self.load_config()
        self.translator.set_provider(self.translation_provider)
        set_preferred_backend(getattr(self, "gemma_backend", "cpu"))
        write_litert_config(self.gemma_backend)
        try:
            self.geometry(self.window_geometry or "900x820")
        except Exception:
            self.geometry("900x820")
        self.apply_active_session(reload_guide=True)
        self.create_widgets()
        self.refresh_session_ui()

        self.capture_manager.set_hotkeys(
            self.translate_hotkey,
            self.assistant_hotkey,
            self.stop_overlay_hotkey,
        )
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.bind("<Configure>", self._on_main_configure)
        self._geom_save_after_id = None
        if self.auto_start_gemma:
            self.after(300, self._startup_local_models)

    # ── Sesión activa (propiedades de conveniencia) ──────────────────────────

    @property
    def active_session(self):
        for s in self.sessions:
            if s["id"] == self.active_session_id:
                return s
        return self.sessions[0] if self.sessions else None

    @property
    def translator_region(self):
        s = self.active_session
        return s.get("translator_region") if s else None

    @translator_region.setter
    def translator_region(self, value):
        if self.active_session:
            self.active_session["translator_region"] = value

    @property
    def journal_region(self):
        s = self.active_session
        return s.get("journal_region") if s else None

    @journal_region.setter
    def journal_region(self, value):
        if self.active_session:
            self.active_session["journal_region"] = value

    @property
    def overlay_mode(self):
        s = self.active_session
        mode = (s.get("overlay_mode") if s else None) or "layer"
        return mode if mode in ("layer", "over") else "layer"

    @overlay_mode.setter
    def overlay_mode(self, value):
        if self.active_session:
            mode = value if value in ("layer", "over") else "layer"
            self.active_session["overlay_mode"] = mode

    # ── UI ───────────────────────────────────────────────────────────────────

    def create_widgets(self):
        status_frame = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=0)
        status_frame.pack(fill="x", side="bottom")

        self.status_label = ctk.CTkLabel(
            status_frame,
            text="Listo",
            font=ctk.CTkFont(size=12),
            text_color=theme.SUCCESS,
        )
        self.status_label.pack(pady=theme.PAD_SM)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=theme.PAD_LG, pady=(theme.PAD, 0))

        ctk.CTkLabel(
            top,
            text="Estilo Kaio",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=theme.TEXT,
        ).pack(side="left")

        self.create_sessions_section(parent=top)

        self.create_gemma_panel()

        self.tabs = ctk.CTkTabview(
            self,
            height=520,
            fg_color=theme.BG,
            command=self._on_tab_changed,
        )
        self.tabs.pack(fill="both", expand=True, padx=theme.PAD_LG, pady=theme.PAD_SM)

        tab_guide = self.tabs.add("Guía")
        tab_translator = self.tabs.add("Traductor")
        tab_hotkeys = self.tabs.add("Atajos")

        self.create_assistant_section(tab_guide)
        self.create_translator_section(tab_translator)
        self.create_hotkeys_section(tab_hotkeys)

        self.tabs.set("Guía")
        self._update_conditional_ui()

    def _sep(self, parent):
        ctk.CTkFrame(parent, height=1, fg_color=theme.BORDER).pack(
            fill="x", padx=theme.PAD, pady=theme.PAD_SM
        )

    def create_gemma_panel(self):
        """Barra universal Gemma (guía + traducción local / híbrida)."""
        self.gemma_panel = ctk.CTkFrame(
            self, fg_color=theme.SURFACE, corner_radius=8, border_width=1, border_color=theme.BORDER
        )
        self.gemma_panel.pack(fill="x", padx=theme.PAD_LG, pady=(theme.PAD_SM, 0))

        head = ctk.CTkFrame(self.gemma_panel, fg_color="transparent")
        head.pack(fill="x", padx=theme.PAD, pady=(theme.PAD_SM, 4))
        ctk.CTkLabel(
            head,
            text="Gemma (IA local)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=theme.TEXT,
        ).pack(side="left")
        ctk.CTkLabel(
            head,
            text="Guía · traducción Gemma / Google+Gemma",
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
        ).pack(side="left", padx=(10, 0))

        gemma_row = ctk.CTkFrame(self.gemma_panel, fg_color="transparent")
        gemma_row.pack(fill="x", padx=theme.PAD, pady=(0, 4))

        ctk.CTkButton(
            gemma_row,
            text="Setup",
            command=self.setup_gemma_quick,
            width=70,
            height=30,
            fg_color=theme.SECONDARY,
            hover_color=theme.SECONDARY_HOVER,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            gemma_row,
            text="Iniciar",
            command=self.start_gemma_quick,
            width=80,
            height=30,
            fg_color=theme.SECONDARY,
            hover_color=theme.SECONDARY_HOVER,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            gemma_row,
            text="Detener",
            command=self.stop_gemma_quick,
            width=80,
            height=30,
            fg_color=theme.DANGER,
            hover_color=theme.DANGER_HOVER,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            gemma_row,
            text="Borrar viejos",
            command=self.purge_gemma_legacy_quick,
            width=90,
            height=30,
            fg_color=theme.SECONDARY,
            hover_color=theme.SECONDARY_HOVER,
        ).pack(side="left")

        backend_row = ctk.CTkFrame(self.gemma_panel, fg_color="transparent")
        backend_row.pack(fill="x", padx=theme.PAD, pady=(0, 2))
        ctk.CTkLabel(
            backend_row,
            text="Memoria",
            font=ctk.CTkFont(size=12),
            text_color=theme.TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))
        self._gemma_backend_label_to_id = {
            label: key for key, label in BACKEND_LABELS.items()
        }
        self.gemma_backend_combo = ctk.CTkComboBox(
            backend_row,
            values=list(self._gemma_backend_label_to_id.keys()),
            width=160,
            command=self.on_gemma_backend_changed,
            fg_color=theme.SURFACE_2,
            border_color=theme.BORDER,
        )
        self.gemma_backend_combo.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            backend_row,
            text=f"Modelo: {DEFAULT_MODEL}",
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
        ).pack(side="left")

        self.gemma_status_label = ctk.CTkLabel(
            self.gemma_panel,
            text=self._gemma_status_text(),
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
        )
        self.gemma_status_label.pack(anchor="w", padx=theme.PAD, pady=(2, 2))

        self.auto_start_gemma_var = ctk.BooleanVar(value=self.auto_start_gemma)
        ctk.CTkCheckBox(
            self.gemma_panel,
            text="Iniciar Gemma al abrir Estilo Kaio",
            variable=self.auto_start_gemma_var,
            command=self.on_auto_start_changed,
            font=ctk.CTkFont(size=12),
            text_color=theme.TEXT_MUTED,
        ).pack(anchor="w", padx=theme.PAD, pady=(0, theme.PAD_SM))

    def _on_tab_changed(self, _tab_name=None):
        # Gemma queda fija; solo Layer/Over sigue siendo condicional
        self._update_layer_controls_visibility()

    def _update_conditional_ui(self):
        """Sincroniza controles condicionales (Layer vs Over)."""
        self._update_layer_controls_visibility()

    def _update_layer_controls_visibility(self):
        """Colocar ventana: solo con vista Layer."""
        if not hasattr(self, "layer_controls_frame"):
            return
        mode = getattr(self, "overlay_mode", "layer") or "layer"
        packed = self.layer_controls_frame.winfo_manager() == "pack"
        if mode == "layer" and not packed:
            kwargs = {"anchor": "w", "fill": "x", "pady": (theme.PAD_SM, 0)}
            if hasattr(self, "translator_hotkey_label"):
                kwargs["before"] = self.translator_hotkey_label
            self.layer_controls_frame.pack(**kwargs)
        elif mode != "layer" and packed:
            self.layer_controls_frame.pack_forget()

    def create_sessions_section(self, parent=None):
        parent = parent or self
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(side="right")

        ctk.CTkLabel(
            row, text="Sesión", font=ctk.CTkFont(size=12), text_color=theme.TEXT_MUTED
        ).pack(side="left", padx=(0, 6))

        self.session_combo = ctk.CTkComboBox(
            row,
            values=["Sesión principal"],
            command=self.on_session_selected,
            width=180,
            font=ctk.CTkFont(size=12),
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
        )
        self.session_combo.pack(side="left", padx=(0, 6))

        self.session_actions = ctk.CTkOptionMenu(
            row,
            values=["Acciones…", "Nueva sesión", "Renombrar", "Eliminar"],
            command=self._on_session_action,
            width=120,
            fg_color=theme.SECONDARY,
            button_color=theme.SECONDARY,
            button_hover_color=theme.SECONDARY_HOVER,
        )
        self.session_actions.set("Acciones…")
        self.session_actions.pack(side="left")

    def _on_session_action(self, choice: str):
        self.session_actions.set("Acciones…")
        if choice == "Nueva sesión":
            self.new_session()
        elif choice == "Renombrar":
            self.rename_session()
        elif choice == "Eliminar":
            self.delete_session()

    def create_hotkeys_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=theme.PAD, pady=theme.PAD)

        ctk.CTkLabel(
            frame,
            text="Atajos de teclado",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=theme.TEXT,
        ).pack(anchor="w", pady=(theme.PAD_SM, 4))

        ctk.CTkLabel(
            frame,
            text="Formato: alt+t, ctrl+shift+t, f8…",
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
        ).pack(anchor="w", pady=(0, theme.PAD_SM))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_SM)

        ctk.CTkLabel(
            row, text="Traducir", font=ctk.CTkFont(size=12), text_color=theme.TEXT_MUTED
        ).pack(side="left", padx=(0, 6))
        self.translate_hotkey_entry = ctk.CTkEntry(
            row,
            width=120,
            font=ctk.CTkFont(size=12),
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
        )
        self.translate_hotkey_entry.insert(0, self.translate_hotkey)
        self.translate_hotkey_entry.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            row, text="Guía", font=ctk.CTkFont(size=12), text_color=theme.TEXT_MUTED
        ).pack(side="left", padx=(0, 6))
        self.assistant_hotkey_entry = ctk.CTkEntry(
            row,
            width=120,
            font=ctk.CTkFont(size=12),
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
        )
        self.assistant_hotkey_entry.insert(0, self.assistant_hotkey)
        self.assistant_hotkey_entry.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            row,
            text="Cerrar overlay",
            font=ctk.CTkFont(size=12),
            text_color=theme.TEXT_MUTED,
        ).pack(side="left", padx=(0, 6))
        self.stop_overlay_hotkey_entry = ctk.CTkEntry(
            row,
            width=120,
            font=ctk.CTkFont(size=12),
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
        )
        self.stop_overlay_hotkey_entry.insert(0, self.stop_overlay_hotkey)
        self.stop_overlay_hotkey_entry.pack(side="left")

        ctk.CTkLabel(
            frame,
            text="Traducir NO es continuo: solo al pulsar el atajo. "
            "Cerrar overlay apaga Over/Layer (también ESC / click derecho en Over).",
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

        ctk.CTkButton(
            frame,
            text="Aplicar atajos",
            width=160,
            height=36,
            command=self.apply_hotkeys_from_ui,
            fg_color=theme.PRIMARY,
            hover_color=theme.PRIMARY_HOVER,
        ).pack(anchor="w", pady=theme.PAD)

        self._sep(frame)

        ctk.CTkLabel(
            frame,
            text="Motor OCR",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=theme.TEXT,
        ).pack(anchor="w", pady=(theme.PAD_SM, 4))

        ocr_engine_row = ctk.CTkFrame(frame, fg_color="transparent")
        ocr_engine_row.pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            ocr_engine_row,
            text="Motor (esta sesión)",
            font=ctk.CTkFont(size=12),
            text_color=theme.TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))
        self._ocr_engine_label_to_id = {
            "OneOCR (recomendado)": "oneocr",
            "EasyOCR": "easyocr",
            "Windows OCR": "winrt",
        }
        self.ocr_engine_combo = ctk.CTkComboBox(
            ocr_engine_row,
            values=list(self._ocr_engine_label_to_id.keys()),
            width=220,
            command=self.on_ocr_engine_changed,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
        )
        self.ocr_engine_combo.pack(side="left")

        self.ocr_status_label = ctk.CTkLabel(
            frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=theme.TEXT_MUTED,
            wraplength=640,
            justify="left",
        )
        self.ocr_status_label.pack(anchor="w", pady=(4, 6))

        ocr_btns = ctk.CTkFrame(frame, fg_color="transparent")
        ocr_btns.pack(anchor="w", pady=4)

        ctk.CTkButton(
            ocr_btns,
            text="Actualizar OCR",
            width=120,
            height=32,
            command=self._refresh_ocr_status,
            fg_color=theme.SECONDARY,
            hover_color=theme.SECONDARY_HOVER,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            ocr_btns,
            text="Preparar OneOCR",
            width=130,
            height=32,
            command=self.prepare_oneocr_quick,
            fg_color=theme.SECONDARY,
            hover_color=theme.SECONDARY_HOVER,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            ocr_btns,
            text="Instalar EasyOCR",
            width=130,
            height=32,
            command=self.install_easyocr_quick,
            fg_color=theme.SECONDARY,
            hover_color=theme.SECONDARY_HOVER,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            ocr_btns,
            text="Idiomas WinRT",
            width=120,
            height=32,
            command=self.open_windows_language_settings,
            fg_color=theme.SECONDARY,
            hover_color=theme.SECONDARY_HOVER,
        ).pack(side="left")

        ctk.CTkLabel(
            frame,
            text="Correcciones OCR: editá guias/ocr_dic.txt (ej. moon=Moon, goas=gods).",
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(theme.PAD_SM, theme.PAD))

        self._refresh_ocr_status()

    def create_translator_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=theme.PAD, pady=theme.PAD)

        ctk.CTkLabel(
            frame,
            text="Traductor",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=theme.TEXT,
        ).pack(anchor="w", pady=(theme.PAD_SM, theme.PAD_SM))

        ctk.CTkButton(
            frame,
            text="Región del traductor",
            command=self.select_translator_region,
            width=280,
            height=40,
            font=ctk.CTkFont(size=14),
            fg_color=theme.PRIMARY,
            hover_color=theme.PRIMARY_HOVER,
        ).pack(anchor="w", pady=(0, 6))

        self.translator_info_label = ctk.CTkLabel(
            frame,
            text=self.get_region_text(self.translator_region, "traductor"),
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
        )
        self.translator_info_label.pack(anchor="w", pady=(0, theme.PAD_SM))

        lang_row = ctk.CTkFrame(frame, fg_color="transparent")
        lang_row.pack(anchor="w", pady=theme.PAD_SM)

        labels = [f"{v} ({k})" for k, v in TRANSLATOR_LANGUAGES.items()]
        self._translator_label_to_code = {
            f"{v} ({k})": k for k, v in TRANSLATOR_LANGUAGES.items()
        }

        ctk.CTkLabel(
            lang_row, text="De", font=ctk.CTkFont(size=12), text_color=theme.TEXT_MUTED
        ).pack(side="left", padx=(0, 6))
        self.source_combo = ctk.CTkComboBox(
            lang_row,
            values=labels,
            width=160,
            command=self.on_translator_langs_changed,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
        )
        self.source_combo.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            lang_row, text="→", font=ctk.CTkFont(size=14), text_color=theme.TEXT_MUTED
        ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            lang_row, text="A", font=ctk.CTkFont(size=12), text_color=theme.TEXT_MUTED
        ).pack(side="left", padx=(0, 6))
        self.target_combo = ctk.CTkComboBox(
            lang_row,
            values=labels,
            width=160,
            command=self.on_translator_langs_changed,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
        )
        self.target_combo.pack(side="left")

        provider_row = ctk.CTkFrame(frame, fg_color="transparent")
        provider_row.pack(fill="x", pady=(theme.PAD, 4))
        ctk.CTkLabel(
            provider_row,
            text="Motor de traducción",
            font=ctk.CTkFont(size=12),
            text_color=theme.TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))
        self._translation_provider_label_to_id = {
            label: key for key, label in TRANSLATION_PROVIDERS.items()
        }
        self.translation_provider_combo = ctk.CTkComboBox(
            provider_row,
            values=list(self._translation_provider_label_to_id.keys()),
            width=320,
            command=self.on_translation_provider_changed,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
        )
        self.translation_provider_combo.pack(side="left", padx=(0, 8))
        self.translation_provider_hint = ctk.CTkLabel(
            frame,
            text=self._translation_provider_hint_text(),
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
        )
        self.translation_provider_hint.pack(anchor="w", pady=(0, 4))

        mode_row = ctk.CTkFrame(frame, fg_color="transparent")
        mode_row.pack(anchor="w", pady=(theme.PAD_SM, 4))
        ctk.CTkLabel(
            mode_row,
            text="Vista (esta sesión)",
            font=ctk.CTkFont(size=12),
            text_color=theme.TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))
        self.overlay_mode_combo = ctk.CTkComboBox(
            mode_row,
            values=["Layer (ventana)", "Over (sobre el juego)"],
            width=220,
            command=self.on_overlay_mode_changed,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
        )
        self.overlay_mode_combo.pack(side="left")

        self.layer_controls_frame = ctk.CTkFrame(frame, fg_color="transparent")
        self.layer_controls_frame.pack(anchor="w", fill="x", pady=(theme.PAD_SM, 0))

        ctk.CTkButton(
            self.layer_controls_frame,
            text="Colocar ventana de traducción",
            command=self.place_overlay_position,
            width=260,
            height=38,
            font=ctk.CTkFont(size=13),
            fg_color=theme.PRIMARY,
            hover_color=theme.PRIMARY_HOVER,
        ).pack(anchor="w", pady=(0, 4))

        self.overlay_pos_label = ctk.CTkLabel(
            self.layer_controls_frame,
            text=self._overlay_pos_text(),
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
        )
        self.overlay_pos_label.pack(anchor="w")

        self.translator_hotkey_label = ctk.CTkLabel(
            frame,
            text=f"Atajo: {self.translate_hotkey.upper()}",
            font=ctk.CTkFont(size=12),
            text_color=theme.TEXT_MUTED,
        )
        self.translator_hotkey_label.pack(anchor="w", pady=(theme.PAD, theme.PAD_SM))

    def create_assistant_section(self, parent):
        frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=4, pady=4)

        # Estado de guía (compacto)
        guide_status = ctk.CTkFrame(frame, fg_color=theme.SURFACE, corner_radius=8)
        guide_status.pack(fill="x", padx=theme.PAD, pady=(theme.PAD_SM, theme.PAD_SM))

        self.guide_info_label = ctk.CTkLabel(
            guide_status,
            text="Sin guía en esta sesión",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=theme.TEXT_MUTED,
            justify="left",
            wraplength=640,
        )
        self.guide_info_label.pack(anchor="w", padx=theme.PAD, pady=(theme.PAD_SM, 2))

        self.guide_session_hint = ctk.CTkLabel(
            guide_status,
            text="La guía queda en el perfil de la sesión y se recarga al abrir.",
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
            justify="left",
            wraplength=640,
        )
        self.guide_session_hint.pack(anchor="w", padx=theme.PAD, pady=(0, theme.PAD_SM))

        # Hero: preguntar
        ctk.CTkLabel(
            frame,
            text="¿Dónde estás / qué necesitás?",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=theme.TEXT,
        ).pack(anchor="w", padx=theme.PAD, pady=(theme.PAD, 4))

        ctk.CTkLabel(
            frame,
            text="El asistente ubica ese momento en la guía y traduce el texto (sin inventar).",
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
        ).pack(anchor="w", padx=theme.PAD, pady=(0, 6))

        self.manual_input = ctk.CTkTextbox(
            frame,
            height=100,
            font=ctk.CTkFont(size=13),
            fg_color=theme.SURFACE,
            text_color=theme.TEXT,
            border_color=theme.BORDER,
            border_width=1,
        )
        self.manual_input.pack(fill="x", padx=theme.PAD)
        self.manual_input.bind("<Control-Return>", lambda e: self.manual_consult())

        ask_row = ctk.CTkFrame(frame, fg_color="transparent")
        ask_row.pack(fill="x", padx=theme.PAD, pady=theme.PAD_SM)

        ctk.CTkButton(
            ask_row,
            text="Preguntar",
            command=self.manual_consult,
            width=160,
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=theme.PRIMARY,
            hover_color=theme.PRIMARY_HOVER,
        ).pack(side="left")

        ctk.CTkLabel(
            ask_row,
            text="Ctrl+Enter",
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
        ).pack(side="left", padx=10)

        # Config secundaria
        self._sep(frame)
        ctk.CTkLabel(
            frame,
            text="Guía y sección",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=theme.TEXT,
        ).pack(anchor="w", padx=theme.PAD, pady=(4, 6))

        load_row = ctk.CTkFrame(frame, fg_color="transparent")
        load_row.pack(fill="x", padx=theme.PAD, pady=2)

        ctk.CTkButton(
            load_row,
            text="Cargar .txt",
            command=self.load_guide_file,
            width=120,
            height=32,
            fg_color=theme.SECONDARY,
            hover_color=theme.SECONDARY_HOVER,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            load_row,
            text="Quitar guía",
            command=self.clear_session_guide,
            width=110,
            height=32,
            fg_color=theme.SECONDARY,
            hover_color=theme.SECONDARY_HOVER,
        ).pack(side="left")

        ctk.CTkLabel(
            frame,
            text="Importar desde URL",
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
        ).pack(anchor="w", padx=theme.PAD, pady=(8, 2))

        self.guide_url_entry = ctk.CTkEntry(
            frame,
            height=32,
            font=ctk.CTkFont(size=12),
            placeholder_text="https://…",
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
        )
        self.guide_url_entry.pack(fill="x", padx=theme.PAD, pady=(0, 4))

        self.import_url_btn = ctk.CTkButton(
            frame,
            text="Importar URL",
            command=self.import_guide_from_url,
            width=130,
            height=30,
            fg_color=theme.SECONDARY,
            hover_color=theme.SECONDARY_HOVER,
        )
        self.import_url_btn.pack(anchor="w", padx=theme.PAD, pady=(0, 8))

        sec_row = ctk.CTkFrame(frame, fg_color="transparent")
        sec_row.pack(fill="x", padx=theme.PAD, pady=4)

        ctk.CTkLabel(
            sec_row, text="Sección", font=ctk.CTkFont(size=12), text_color=theme.TEXT_MUTED
        ).pack(side="left", padx=(0, 6))

        self.section_combo = ctk.CTkComboBox(
            sec_row,
            values=[SECTION_AUTO],
            width=340,
            font=ctk.CTkFont(size=12),
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
        )
        self.section_combo.set(SECTION_AUTO)
        self.section_combo.pack(side="left", padx=4)

        filter_row = ctk.CTkFrame(frame, fg_color="transparent")
        filter_row.pack(fill="x", padx=theme.PAD, pady=(0, 4))

        ctk.CTkLabel(
            filter_row, text="Filtrar", font=ctk.CTkFont(size=11), text_color=theme.TEXT_MUTED
        ).pack(side="left", padx=(0, 6))

        self.section_filter_entry = ctk.CTkEntry(
            filter_row,
            width=220,
            font=ctk.CTkFont(size=12),
            placeholder_text="ej. bosque, boss…",
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
        )
        self.section_filter_entry.pack(side="left", padx=4)
        self.section_filter_entry.bind("<KeyRelease>", lambda e: self._refresh_section_combo())

        self.section_warn_label = ctk.CTkLabel(
            frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=theme.WARNING,
            wraplength=640,
            justify="left",
        )
        self.section_warn_label.pack(anchor="w", pady=(0, 6), padx=theme.PAD)

        # Idioma respuesta guía
        self._sep(frame)
        resp_row = ctk.CTkFrame(frame, fg_color="transparent")
        resp_row.pack(fill="x", padx=theme.PAD, pady=4)

        ctk.CTkLabel(
            resp_row,
            text="Idioma respuesta",
            font=ctk.CTkFont(size=12),
            text_color=theme.TEXT_MUTED,
        ).pack(side="left", padx=(0, 6))

        assistant_labels = [f"{v} ({k})" for k, v in ASSISTANT_LANGUAGES.items()]
        self._assistant_label_to_code = {
            f"{v} ({k})": k for k, v in ASSISTANT_LANGUAGES.items()
        }

        self.assistant_lang_combo = ctk.CTkComboBox(
            resp_row,
            values=assistant_labels,
            width=180,
            command=self.on_assistant_lang_changed,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
        )
        self.assistant_lang_combo.pack(side="left")

        self._sep(frame)
        ctk.CTkLabel(
            frame,
            text="Captura del diario (OCR)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=theme.TEXT,
        ).pack(anchor="w", padx=theme.PAD, pady=(4, 6))

        ctk.CTkButton(
            frame,
            text="Región del diario",
            command=self.select_journal_region,
            width=280,
            height=36,
            font=ctk.CTkFont(size=13),
            fg_color=theme.SECONDARY,
            hover_color=theme.SECONDARY_HOVER,
        ).pack(anchor="w", padx=theme.PAD, pady=(0, 4))

        self.journal_info_label = ctk.CTkLabel(
            frame,
            text=self.get_region_text(self.journal_region, "diario"),
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
        )
        self.journal_info_label.pack(anchor="w", padx=theme.PAD, pady=(0, 6))

        self.assistant_hotkey_label = ctk.CTkLabel(
            frame,
            text=f"Atajo diario OCR: {self.assistant_hotkey.upper()}",
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
        )
        self.assistant_hotkey_label.pack(anchor="w", padx=theme.PAD, pady=(theme.PAD_SM, 4))

        ctk.CTkLabel(
            frame,
            text="Gemma (barra arriba) alimenta la guía y la traducción local / híbrida.",
            font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
        ).pack(anchor="w", padx=theme.PAD, pady=(0, theme.PAD))

    # ── Sesiones: lógica ─────────────────────────────────────────────────────

    def refresh_session_ui(self):
        names = [s["name"] for s in self.sessions]
        self.session_combo.configure(values=names or ["(sin sesiones)"])
        active = self.active_session
        if active:
            self.session_combo.set(active["name"])

        # Combos de idioma
        src = active.get("translator_source", "en") if active else "en"
        tgt = active.get("translator_target", "es") if active else "es"
        asst = active.get("assistant_language", "es") if active else "es"

        src_label = next(
            (lab for lab, code in self._translator_label_to_code.items() if code == src),
            list(self._translator_label_to_code.keys())[0],
        )
        tgt_label = next(
            (lab for lab, code in self._translator_label_to_code.items() if code == tgt),
            list(self._translator_label_to_code.keys())[1],
        )
        asst_label = next(
            (lab for lab, code in self._assistant_label_to_code.items() if code == asst),
            list(self._assistant_label_to_code.keys())[0],
        )

        self.source_combo.set(src_label)
        self.target_combo.set(tgt_label)
        self.assistant_lang_combo.set(asst_label)

        src_name = TRANSLATOR_LANGUAGES.get(src, src)
        tgt_name = TRANSLATOR_LANGUAGES.get(tgt, tgt)
        self.translator_hotkey_label.configure(
            text=f"Usa {self.translate_hotkey.upper()} para traducir ({src_name} → {tgt_name})"
        )
        if hasattr(self, "assistant_hotkey_label"):
            self.assistant_hotkey_label.configure(
                text=(
                    f"También podés usar {self.assistant_hotkey.upper()} "
                    "para leer el diario por OCR (si el juego tiene)."
                )
            )
        if hasattr(self, "overlay_mode_combo"):
            if self.overlay_mode == "over":
                self.overlay_mode_combo.set("Over (sobre el juego)")
            else:
                self.overlay_mode_combo.set("Layer (ventana)")
        if hasattr(self, "overlay_pos_label"):
            self.overlay_pos_label.configure(
                text=self._overlay_pos_text(),
                text_color="lime" if self.overlay_position else "gray",
            )
        if hasattr(self, "ocr_engine_combo"):
            eid = (active or {}).get("ocr_engine") or self.default_ocr_engine or "oneocr"
            label = next(
                (lab for lab, code in self._ocr_engine_label_to_id.items() if code == eid),
                "OneOCR (recomendado)",
            )
            self.ocr_engine_combo.set(label)
        self._refresh_ocr_status()

        # Regiones
        color_t = "lime" if self.translator_region else "gray"
        color_j = "lime" if self.journal_region else "gray"
        self.translator_info_label.configure(
            text=self.get_region_text(self.translator_region, "traductor"),
            text_color=color_t,
        )
        self.journal_info_label.configure(
            text=self.get_region_text(self.journal_region, "diario"),
            text_color=color_j,
        )

        # Guía
        self._update_guide_info_label()
        if self.guide_text and not self.guide_sections:
            self._rebuild_guide_sections()
        elif hasattr(self, "section_combo"):
            self._refresh_section_combo()
        self._sync_gemma_backend_combo()
        self._sync_translation_provider_combo()
        self._update_conditional_ui()

    def apply_active_session(self, reload_guide=False):
        s = self.active_session
        if not s:
            return

        self.translator.set_languages(
            s.get("translator_source", "en"),
            s.get("translator_target", "es"),
        )
        self.translator.set_provider(self.translation_provider)
        self.capture_manager.ocr_engine.set_language(s.get("translator_source", "en"))
        ocr_id = s.get("ocr_engine") or self.default_ocr_engine or "oneocr"
        self.capture_manager.ocr_engine.set_engine(ocr_id)

        if reload_guide:
            self._load_guide_from_path(s.get("guide_path", ""))
            if not s.get("guide_path"):
                self.guide_text = ""
                self.guide_sections = []
                self._update_guide_info_label()
                if hasattr(self, "section_combo"):
                    self._refresh_section_combo()

    def on_session_selected(self, name):
        # Guardar estado actual antes de cambiar
        self.save_config()

        for s in self.sessions:
            if s["name"] == name:
                self.active_session_id = s["id"]
                break

        self.apply_active_session(reload_guide=True)
        self.refresh_session_ui()
        self.save_config()
        self.update_status(f"Sesión activa: {name}", "lime")

    def new_session(self):
        name = simpledialog.askstring(
            "Nueva sesión",
            "Nombre de la sesión\n(ej: 'Persona 5 JP', 'Elden Ring guía'):",
            parent=self,
        )
        if not name or not name.strip():
            return
        name = name.strip()
        if any(s["name"] == name for s in self.sessions):
            messagebox.showwarning("Duplicado", "Ya existe una sesión con ese nombre.")
            return

        self.save_config()
        session = default_session(name)
        self.sessions.append(session)
        self.active_session_id = session["id"]
        self.guide_text = ""
        self.guide_sections = []
        self.apply_active_session(reload_guide=True)
        self.refresh_session_ui()
        self.save_config()
        self.update_status(f"Sesión creada: {name}", "lime")

    def rename_session(self):
        s = self.active_session
        if not s:
            return
        name = simpledialog.askstring(
            "Renombrar sesión",
            "Nuevo nombre:",
            initialvalue=s["name"],
            parent=self,
        )
        if not name or not name.strip():
            return
        name = name.strip()
        if any(x["name"] == name and x["id"] != s["id"] for x in self.sessions):
            messagebox.showwarning("Duplicado", "Ya existe una sesión con ese nombre.")
            return
        s["name"] = name
        self.refresh_session_ui()
        self.save_config()

    def delete_session(self):
        if len(self.sessions) <= 1:
            messagebox.showwarning(
                "No se puede eliminar",
                "Debe quedar al menos una sesión.",
            )
            return
        s = self.active_session
        if not s:
            return
        if not messagebox.askyesno(
            "Eliminar sesión",
            f"¿Eliminar la sesión '{s['name']}'?\nSe perderán su guía, regiones e idiomas.",
        ):
            return
        self.sessions = [x for x in self.sessions if x["id"] != s["id"]]
        self.active_session_id = self.sessions[0]["id"]
        self.apply_active_session(reload_guide=True)
        self.refresh_session_ui()
        self.save_config()
        self.update_status(f"Sesión activa: {self.active_session['name']}", "lime")

    def on_translator_langs_changed(self, _=None):
        s = self.active_session
        if not s:
            return
        src = self._translator_label_to_code.get(self.source_combo.get(), "en")
        tgt = self._translator_label_to_code.get(self.target_combo.get(), "es")
        s["translator_source"] = src
        s["translator_target"] = tgt
        self.translator.set_languages(src, tgt)
        self.capture_manager.ocr_engine.set_language(src)
        self._refresh_ocr_status()
        src_name = TRANSLATOR_LANGUAGES.get(src, src)
        tgt_name = TRANSLATOR_LANGUAGES.get(tgt, tgt)
        self.translator_hotkey_label.configure(
            text=f"Usa {self.translate_hotkey.upper()} para traducir ({src_name} → {tgt_name})"
        )
        self.save_config()

    def on_assistant_lang_changed(self, _=None):
        s = self.active_session
        if not s:
            return
        code = self._assistant_label_to_code.get(self.assistant_lang_combo.get(), "es")
        s["assistant_language"] = code
        self.save_config()

    # ── Regiones / guía / Ollama ─────────────────────────────────────────────

    def get_region_text(self, region, region_name):
        if region:
            return (
                f"Región {region_name}: X={region['x']}, Y={region['y']}, "
                f"W={region['width']}, H={region['height']}"
            )
        return f"Región {region_name} no definida"

    def select_translator_region(self):
        self.withdraw()
        self.update()

        selector = RegionSelector(self)
        self.wait_window(selector)

        if selector.selected_region:
            self.translator_region = selector.selected_region
            self.translator_info_label.configure(
                text=self.get_region_text(self.translator_region, "traductor"),
                text_color="lime",
            )
            self.save_config()
            self.update_status("Región del traductor guardada correctamente", "lime")

        self.deiconify()

    def select_journal_region(self):
        self.withdraw()
        self.update()

        selector = RegionSelector(self)
        self.wait_window(selector)

        if selector.selected_region:
            self.journal_region = selector.selected_region
            self.journal_info_label.configure(
                text=self.get_region_text(self.journal_region, "diario"),
                text_color="lime",
            )
            self.save_config()
            self.update_status("Región del diario guardada correctamente", "lime")

        self.deiconify()

    def _load_guide_from_path(self, path):
        self.guide_text = ""
        self.guide_sections = []
        if not path:
            self._update_guide_info_label()
            return
        if not os.path.exists(path):
            print(f"Guía no encontrada: {path}")
            self._update_guide_info_label(missing_path=path)
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.guide_text = f.read()
            self._rebuild_guide_sections()
        except Exception as e:
            print(f"Error al cargar guía: {e}")
            self._update_guide_info_label(missing_path=path)

    def clear_session_guide(self):
        if self.active_session:
            self.active_session["guide_path"] = ""
        self.guide_text = ""
        self.guide_sections = []
        if hasattr(self, "section_combo"):
            self._refresh_section_combo()
        self._update_guide_info_label()
        self.save_config()
        self.update_status("Guía quitada de esta sesión", "orange")

    def _rebuild_guide_sections(self):
        self.guide_sections = parse_guide_sections(self.guide_text)
        if hasattr(self, "section_combo"):
            self._refresh_section_combo()
        self._update_guide_info_label()

    def _section_combo_values(self):
        values = [SECTION_AUTO, SECTION_FULL]
        filt = ""
        if hasattr(self, "section_filter_entry"):
            filt = self.section_filter_entry.get().strip()
        visible = filter_sections_by_query(self.guide_sections, filt)
        for s in visible:
            title = s.title if len(s.title) <= 70 else s.title[:67] + "…"
            values.append(f"{s.id}. {title}")
        return values

    def _refresh_section_combo(self):
        if not hasattr(self, "section_combo"):
            return
        current = self.section_combo.get()
        values = self._section_combo_values()
        self.section_combo.configure(values=values)
        if current in values:
            self.section_combo.set(current)
        else:
            self.section_combo.set(SECTION_AUTO)

        warn = ""
        if self.guide_text and len(self.guide_sections) <= 1 and is_long_guide(self.guide_text):
            warn = (
                "Pocas secciones detectadas en una guía larga. "
                "Si podés, elegí mejor el tramo o reformateá títulos."
            )
        elif self.guide_text and is_long_guide(self.guide_text):
            warn = "Guía larga: evitá “Toda la guía”; elegí sección o Auto."
        if hasattr(self, "section_warn_label"):
            self.section_warn_label.configure(text=warn)

    def _update_guide_info_label(self, missing_path=None):
        if not hasattr(self, "guide_info_label"):
            return
        session_name = (
            self.active_session["name"] if self.active_session else "sesión"
        )
        if missing_path:
            self.guide_info_label.configure(
                text=(
                    f"Sesión “{session_name}”: guía vinculada pero no se encontró el archivo\n"
                    f"{missing_path}\nVolvé a cargarla (queda guardada en el perfil)."
                ),
                text_color="orange",
            )
            return
        if not self.guide_text:
            self.guide_info_label.configure(
                text=f"Sesión “{session_name}”: sin guía cargada",
                text_color="gray",
            )
            return
        path = ""
        if self.active_session:
            path = self.active_session.get("guide_path", "")
        name = os.path.basename(path) if path else "guía"
        n = len(self.guide_sections)
        self.guide_info_label.configure(
            text=(
                f"Sesión “{session_name}”: guía activa → {name}\n"
                f"{n} secciones · {len(self.guide_text)} caracteres · se mantiene al reabrir"
            ),
            text_color="lime",
        )

    def _parse_section_selection(self):
        """Devuelve ('auto'|'full'|int_id)."""
        if not hasattr(self, "section_combo"):
            return "auto"
        val = self.section_combo.get()
        if val == SECTION_AUTO:
            return "auto"
        if val == SECTION_FULL:
            return "full"
        try:
            return int(val.split(".", 1)[0].strip())
        except (ValueError, IndexError):
            return "auto"

    def _resolve_guide_context(self, query_text, force_auto=False):
        """
        Devuelve (context_text, error_msg|None).
        error_msg se muestra al usuario y cancela la consulta de tip.
        """
        if not self.guide_text:
            return None, "No hay guía cargada."

        if not self.guide_sections:
            self.guide_sections = parse_guide_sections(self.guide_text)

        mode = "auto" if force_auto else self._parse_section_selection()

        if mode == "full":
            if is_long_guide(self.guide_text):
                # Permitido con advertencia (no bloquea)
                pass
            return self.guide_text, None

        section_id = None
        extra_terms: list[str] | None = None
        if mode == "auto":
            progress = is_progress_query(query_text)
            extra_terms = (
                translate_query_keywords(query_text) if gemma_is_running() else []
            )
            llm_pick = None
            if not progress:
                titles = [s.title for s in self.guide_sections]
                llm_pick = self.guide_assistant.pick_section_index(titles, query_text)
            section_id = resolve_auto_section_id(
                self.guide_sections,
                query_text,
                llm_pick,
                prefer_later=progress,
                extra_terms=extra_terms or None,
            )
            if section_id is None and gemma_is_running():
                titles = [s.title for s in self.guide_sections]
                llm_pick = self.guide_assistant.pick_section_index(titles, query_text)
                section_id = resolve_auto_section_id(
                    self.guide_sections,
                    query_text,
                    llm_pick,
                    prefer_later=progress,
                    extra_terms=extra_terms or None,
                )
            if section_id is None:
                return None, (
                    "No pude ubicar la sección automáticamente (guía en otro idioma o poco contexto). "
                    "Elegí una sección en “Estoy en / sección” y volvé a preguntar."
                )
        elif isinstance(mode, int):
            section_id = mode
        else:
            return self.guide_text, None

        if is_progress_query(query_text):
            if mode == "auto":
                candidates = build_progress_candidate_contexts(
                    self.guide_sections,
                    query_text,
                    max_chars=12000,
                    max_candidates=3,
                    extra_terms=extra_terms,
                )
                if candidates:
                    return [ctx for _sid, ctx in candidates], None
            return (
                build_progress_context(
                    self.guide_sections, section_id, max_chars=12000, lookback=1
                ),
                None,
            )
        return build_context_for_section(self.guide_sections, section_id), None

    def load_guide_file(self):
        file_path = filedialog.askopenfilename(
            title="Seleccionar archivo de guía",
            filetypes=[("Archivos de texto", "*.txt"), ("Todos los archivos", "*.*")],
        )

        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.guide_text = f.read()

                if self.active_session:
                    self.active_session["guide_path"] = file_path

                self._rebuild_guide_sections()
                self.save_config()
                self.update_status(
                    f"Guía de la sesión: {os.path.basename(file_path)} (queda guardada)",
                    "lime",
                )

            except Exception as e:
                messagebox.showerror("Error", f"No se pudo cargar el archivo:\n{str(e)}")

    def import_guide_from_url(self):
        url = self.guide_url_entry.get().strip()
        if not url:
            messagebox.showwarning("URL", "Pegá la URL de la guía.")
            return
        self.import_url_btn.configure(state="disabled")
        self.update_status("Importando guía…", "yellow")

        def worker():
            from .guide_importer import GuideImporter, GuideImportError

            try:
                importer = GuideImporter()

                def progress(cur, total, msg):
                    self.after(
                        0,
                        lambda c=cur, t=total, m=msg: self.update_status(
                            f"{m} ({c}/{t})", "yellow"
                        ),
                    )

                result = importer.import_url(url, progress_cb=progress)
                self.after(0, lambda r=result: self._on_guide_import_ok(r))
            except GuideImportError as e:
                self.after(0, lambda msg=str(e): self._on_guide_import_err(msg))
            except Exception as e:
                self.after(
                    0,
                    lambda msg=f"Error inesperado: {e}": self._on_guide_import_err(msg),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _on_guide_import_ok(self, result):
        self.import_url_btn.configure(state="normal")
        with open(result.path, encoding="utf-8") as f:
            self.guide_text = f.read()
        if self.active_session:
            self.active_session["guide_path"] = result.path
        self._rebuild_guide_sections()
        self.save_config()
        warn = ("; ".join(result.warnings)) if result.warnings else ""
        msg = (
            f"Guía importada ({result.adapter}, {result.pages} pág., "
            f"{result.chars} chars)"
        )
        if warn:
            msg += f" — {warn}"
        self.update_status(msg, "orange" if warn else "lime")
        messagebox.showinfo("Importación", f"Guardada en:\n{result.path}\n\n{msg}")

    def _on_guide_import_err(self, message: str):
        self.import_url_btn.configure(state="normal")
        self.update_status(message, "red")
        messagebox.showerror("Importar URL", message)

    def _gemma_status_text(self) -> str:
        backend = BACKEND_LABELS.get(get_preferred_backend(), get_preferred_backend())
        model_hint = resolve_model_id() if gemma_is_running() else DEFAULT_MODEL
        if gemma_is_running():
            return f"Gemma/LiteRT: en marcha · {model_hint} · {backend}"
        if self.litert_manager.is_installed():
            return f"Gemma/LiteRT: apagado · {model_hint} · {backend} — usá Iniciar"
        return "Gemma/LiteRT: no instalado — usá Setup"

    def _translation_provider_hint_text(self) -> str:
        p = normalize_translation_provider(
            getattr(self, "translation_provider", "argos")
        )
        eta = TRANSLATION_PROVIDER_ETA.get(p, "")
        if p == "argos":
            return (
                f"OCR → Argos offline (sin internet, sin bloqueos). "
                f"Tiempo típico {eta}."
            )
        if p == "argos_gemma":
            return (
                f"OCR → Argos + revisión Gemma (borrador rápido + IA). "
                f"Requiere Gemma iniciado. Tiempo típico {eta}."
            )
        return (
            f"OCR → Gemma local (2 pasadas). "
            f"Requiere Iniciar si está apagado. Tiempo típico {eta}."
        )

    def on_translation_provider_changed(self, choice=None):
        label = choice or (
            self.translation_provider_combo.get()
            if hasattr(self, "translation_provider_combo")
            else ""
        )
        provider = self._translation_provider_label_to_id.get(label, "gemma")
        self.translation_provider = provider
        self.translator.set_provider(provider)
        if hasattr(self, "translation_provider_hint"):
            self.translation_provider_hint.configure(
                text=self._translation_provider_hint_text()
            )
        self.save_config()
        name = TRANSLATION_PROVIDERS.get(provider, provider)
        self.update_status(f"Motor de traducción: {name}", "lime")
        # Gemma queda visible siempre; solo Layer/Over es condicional
        self._update_layer_controls_visibility()

    def _sync_translation_provider_combo(self):
        if not hasattr(self, "translation_provider_combo"):
            return
        provider = getattr(self, "translation_provider", "argos")
        provider = normalize_translation_provider(provider)
        if provider not in TRANSLATION_PROVIDERS:
            provider = "argos"
        label = TRANSLATION_PROVIDERS[provider]
        self.translation_provider_combo.set(label)
        if hasattr(self, "translation_provider_hint"):
            self.translation_provider_hint.configure(
                text=self._translation_provider_hint_text()
            )

    def on_gemma_backend_changed(self, choice=None):
        label = choice or (
            self.gemma_backend_combo.get() if hasattr(self, "gemma_backend_combo") else ""
        )
        backend = self._gemma_backend_label_to_id.get(label, "cpu")
        self.gemma_backend = backend
        set_preferred_backend(backend)
        write_litert_config(backend)
        self._refresh_gemma_status()
        self.save_config()
        if gemma_is_running():
            self.update_status(
                "Backend guardado. Reiniciá Gemma (Detener → Iniciar) para aplicarlo.",
                "orange",
            )

    def _sync_gemma_backend_combo(self):
        if not hasattr(self, "gemma_backend_combo"):
            return
        backend = getattr(self, "gemma_backend", "cpu")
        label = BACKEND_LABELS.get(backend, BACKEND_LABELS["cpu"])
        self.gemma_backend_combo.set(label)

    def _refresh_gemma_status(self):
        try:
            self.gemma_status_label.configure(text=self._gemma_status_text())
        except Exception:
            pass

    def setup_gemma_quick(self):
        if not messagebox.askyesno(
            "Setup Gemma",
            f"Se instalará litert-lm y Gemma 4 E4B (~3.7 GB).\n"
            "Se borrarán modelos viejos (E2B) si existen.\n"
            "Necesita internet solo esta vez. ¿Continuar?",
        ):
            return
        self.update_status("Setup Gemma en curso…", "yellow")

        def worker():
            try:
                import subprocess

                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--upgrade",
                        "litert-lm>=0.16.0",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                self.litert_manager.import_model(
                    progress=lambda m: self.after(
                        0, lambda msg=m: self.update_status(msg, "yellow")
                    ),
                    model_id=DEFAULT_MODEL,
                )
                self.after(
                    0,
                    lambda: (
                        self.update_status("Setup Gemma OK", "lime"),
                        self._refresh_gemma_status(),
                        messagebox.showinfo(
                            "Gemma",
                            "Modelo listo. Pulsá Iniciar y después usá el atajo de traducir.",
                        ),
                    ),
                )
            except Exception as e:
                err = str(e)
                self.after(
                    0,
                    lambda m=err: (
                        self.update_status(f"Setup Gemma falló: {m}", "red"),
                        messagebox.showerror("Setup Gemma", m),
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def start_gemma_quick(self):
        self.update_status("Iniciando Gemma (LiteRT)…", "yellow")

        def worker():
            try:
                self.litert_manager.start_server(
                    progress=lambda m: self.after(
                        0, lambda msg=m: self.update_status(msg, "yellow")
                    ),
                    backend=self.gemma_backend,
                )
                self.after(
                    0,
                    lambda: (
                        self.update_status("Gemma (LiteRT) listo", "lime"),
                        self._refresh_gemma_status(),
                    ),
                )
            except Exception as e:
                err = str(e)
                self.after(
                    0,
                    lambda m=err: (
                        self.update_status(m, "red"),
                        messagebox.showerror("Gemma", m),
                        self._refresh_gemma_status(),
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def stop_gemma_quick(self):
        if not messagebox.askyesno(
            "Detener Gemma",
            "Se cerrará el servidor LiteRT-LM.\n¿Continuar?",
        ):
            return
        result = self.litert_manager.stop_server()
        self._refresh_gemma_status()
        if result.get("killed"):
            self.update_status("Gemma (LiteRT) detenido", "orange")
        else:
            self.update_status("No había proceso LiteRT activo", "orange")

    def purge_gemma_legacy_quick(self):
        if not messagebox.askyesno(
            "Borrar modelos viejos",
            "Se eliminarán gemma4-e2b y otros modelos legacy de LiteRT.\n"
            "¿Continuar?",
        ):
            return
        try:
            removed = self.litert_manager.purge_legacy_models()
            self._refresh_gemma_status()
            if removed:
                self.update_status(f"Eliminados: {', '.join(removed)}", "lime")
                messagebox.showinfo("Listo", "Modelos borrados:\n" + "\n".join(removed))
            else:
                self.update_status("No había modelos viejos", "orange")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def open_ollama_setup(self):
        messagebox.showinfo(
            "Gemma unificado",
            "Ollama ya no se usa. Traducción y guía usan Gemma/LiteRT.\n"
            "Configuralo en la pestaña Traductor.",
        )

    def stop_ollama_quick(self):
        self.stop_gemma_quick()

    def start_ollama_quick(self):
        self.start_gemma_quick()

    def manual_consult(self):
        query = self.manual_input.get("1.0", "end-1c").strip()

        if not query:
            messagebox.showwarning(
                "Pregunta vacía",
                "Escribí dónde estás o qué necesitás saber.\n\n"
                "Ejemplo: Estoy en el pueblo, el NPC me habló de una cueva. ¿Qué hago?",
            )
            return

        if not self.guide_text:
            messagebox.showwarning(
                "Sin guía",
                "Cargá primero un archivo de guía (.txt) con el botón de arriba.",
            )
            return

        self.update_status("Preguntando a la guía…", "yellow")
        self.consult_ollama(query)

    def update_status(self, message, color="lime"):
        self.status_label.configure(text=f"Estado: {message}", text_color=color)

    def _overlay_pos_text(self):
        if self.overlay_position:
            return (
                f"Posición overlay: X={self.overlay_position['x']}, "
                f"Y={self.overlay_position['y']} (también puedes arrastrar la ventana)"
            )
        return "Posición overlay: centrada abajo (arrastra la ventana o usa 'Colocar')"

    def _refresh_ocr_status(self):
        if not hasattr(self, "ocr_status_label"):
            return
        engine = self.capture_manager.ocr_engine
        msg = engine.status_message()
        if not engine.status_ok():
            color = "orange"
        elif engine.needs_language_pack():
            color = "orange"
        else:
            color = "lime"
        self.ocr_status_label.configure(text=msg.replace("\n", " · "), text_color=color)

    def on_ocr_engine_changed(self, choice=None):
        label = choice or self.ocr_engine_combo.get()
        eid = self._ocr_engine_label_to_id.get(label, "oneocr")
        s = self.active_session
        if s is not None:
            s["ocr_engine"] = eid
        self.capture_manager.ocr_engine.set_engine(eid)
        self.save_config()
        self._refresh_ocr_status()
        from .ocr_engine import ENGINE_LABELS

        self.update_status(f"Motor OCR: {ENGINE_LABELS.get(eid, eid)}", "cyan")

    def on_auto_start_changed(self):
        self.auto_start_gemma = bool(
            getattr(self, "auto_start_gemma_var", ctk.BooleanVar(value=False)).get()
        )
        self.gemma_backend = self._gemma_backend_label_to_id.get(
            getattr(self, "gemma_backend_combo", None) and self.gemma_backend_combo.get()
            or BACKEND_LABELS.get(self.gemma_backend, "RAM (CPU)"),
            getattr(self, "gemma_backend", "cpu"),
        )
        set_preferred_backend(self.gemma_backend)
        write_litert_config(self.gemma_backend)
        self.save_config()

    def prepare_oneocr_quick(self):
        self.update_status("Preparando OneOCR (Snipping Tool)…", "yellow")

        def worker():
            ok = self.capture_manager.ocr_engine.prepare_oneocr()
            msg = "OneOCR listo" if ok else "OneOCR: no se pudo preparar"
            color = "lime" if ok else "orange"
            self.after(0, lambda: (self._refresh_ocr_status(), self.update_status(msg, color)))

        threading.Thread(target=worker, daemon=True).start()

    def install_easyocr_quick(self):
        bat = os.path.join(repo_root(), "scripts", "Setup_EasyOCR.bat")
        if not os.path.isfile(bat):
            messagebox.showerror("EasyOCR", f"No encontré:\n{bat}")
            return
        if not messagebox.askyesno(
            "Instalar EasyOCR",
            "Se instalará easyocr + dependencias (puede tardar varios minutos).\n¿Continuar?",
        ):
            return
        self.update_status("Instalando EasyOCR…", "yellow")

        def worker():
            import subprocess

            try:
                r = subprocess.run(
                    [bat],
                    cwd=os.path.dirname(bat),
                    capture_output=True,
                    text=True,
                    timeout=3600,
                    shell=True,
                )
                ok = r.returncode == 0
                tail = (r.stdout or r.stderr or "")[-400:]
                msg = "EasyOCR instalado" if ok else f"EasyOCR falló: {tail}"
                color = "lime" if ok else "red"
            except Exception as e:
                msg = f"EasyOCR: {e}"
                color = "red"
            self.after(0, lambda: (self._refresh_ocr_status(), self.update_status(msg, color)))

        threading.Thread(target=worker, daemon=True).start()

    def open_windows_language_settings(self):
        """Abre Configuración → Idioma y región (para instalar packs OCR)."""
        try:
            # URI de Settings en Windows 10/11
            os.startfile("ms-settings:regionlanguage")
            self.update_status(
                "Abrí Configuración de Windows → agregá el idioma e instalá OCR",
                "cyan",
            )
            messagebox.showinfo(
                "Packs OCR de Windows",
                "Se abrió Configuración → Idioma y región.\n\n"
                "1. Agregá el idioma del juego (ej. English o 日本語).\n"
                "2. En opciones del idioma, instalá "
                "“Reconocimiento óptico de caracteres”.\n"
                "3. Volvé acá y tocá “Actualizar estado OCR”.",
            )
        except Exception as e:
            messagebox.showerror(
                "Error",
                f"No se pudo abrir la configuración:\n{e}\n\n"
                "Abrila manualmente: Configuración → Hora e idioma → Idioma y región.",
            )

    def apply_hotkeys_from_ui(self):
        translate = self.translate_hotkey_entry.get().strip().lower()
        assistant = self.assistant_hotkey_entry.get().strip().lower()
        stop_ov = "alt+x"
        if hasattr(self, "stop_overlay_hotkey_entry"):
            stop_ov = self.stop_overlay_hotkey_entry.get().strip().lower() or "alt+x"
        if not translate or not assistant:
            messagebox.showwarning("Atajos", "Ambos atajos deben tener un valor.")
            return
        if len({translate, assistant, stop_ov}) < 3:
            messagebox.showwarning(
                "Atajos", "Traducir, Guía y Cerrar overlay deben ser distintos."
            )
            return
        try:
            self.capture_manager.set_hotkeys(translate, assistant, stop_ov)
            self.translate_hotkey = translate
            self.assistant_hotkey = assistant
            self.stop_overlay_hotkey = stop_ov
            self.save_config()
            self.refresh_session_ui()
            messagebox.showinfo(
                "Atajos aplicados",
                f"Traducir: {translate.upper()}\n"
                f"Guía: {assistant.upper()}\n"
                f"Cerrar overlay: {stop_ov.upper()}",
            )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron aplicar los atajos:\n{e}")

    def close_translation_overlays(self):
        """Cierra Over (ventanitas) y Layer (ventana grande)."""
        closed = False
        over = getattr(self, "_over_overlay", None)
        if over is not None:
            try:
                over.destroy()
                closed = True
            except Exception:
                pass
            self._over_overlay = None
        layer = getattr(self, "_layer_overlay", None)
        if layer is not None:
            try:
                layer.destroy()
                closed = True
            except Exception:
                pass
            self._layer_overlay = None
        if closed:
            self.update_status("Overlay cerrado", "lime")
        else:
            self.update_status("No hay overlay abierto", "orange")

    def on_overlay_mode_changed(self, choice=None):
        label = choice or (
            self.overlay_mode_combo.get() if hasattr(self, "overlay_mode_combo") else ""
        )
        self.overlay_mode = "over" if "Over" in (label or "") else "layer"
        self.save_config()
        sess = (self.active_session or {}).get("name") or "sesión"
        mode_name = "Over" if self.overlay_mode == "over" else "Layer"
        self.update_status(f"{sess}: vista {mode_name}", "cyan")
        self._update_conditional_ui()

    def on_overlay_position_changed(self, pos):
        self.overlay_position = pos
        if hasattr(self, "overlay_pos_label"):
            self.overlay_pos_label.configure(text=self._overlay_pos_text(), text_color="lime")
        self.save_config()

    def place_overlay_position(self):
        """Muestra una ventana de prueba para colocar el overlay arrastrándola."""
        TranslatorOverlay(
            self,
            "Arrastra esta ventana al lugar donde quieres ver las traducciones.\n"
            "Al soltar se guarda la posición. ESC para cerrar.",
            source_label="Posición",
            target_label="Overlay",
            position=self.overlay_position,
            on_position_changed=self.on_overlay_position_changed,
            auto_close_ms=0,
        )
        self.update_status("Arrastra el overlay y suéltalo donde quieras", "cyan")

    # ── Config persistente ───────────────────────────────────────────────────

    def save_config(self):
        try:
            self.window_geometry = self.geometry()
        except Exception:
            pass
        config = {
            "active_session_id": self.active_session_id,
            "sessions": self.sessions,
            "translate_hotkey": self.translate_hotkey,
            "assistant_hotkey": self.assistant_hotkey,
            "stop_overlay_hotkey": self.stop_overlay_hotkey,
            "overlay_position": self.overlay_position,
            "window_geometry": self.window_geometry,
            "response_geometry": self.response_geometry,
            "auto_start_gemma": self.auto_start_gemma,
            "gemma_backend": getattr(self, "gemma_backend", "cpu"),
            "default_ocr_engine": getattr(self, "default_ocr_engine", "oneocr"),
            "translation_provider": getattr(self, "translation_provider", "gemma"),
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error al guardar configuración: {e}")

    def load_config(self):
        config_path = resolve_config_path()
        if not os.path.exists(config_path):
            session = default_session()
            self.sessions = [session]
            self.active_session_id = session["id"]
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            self.translate_hotkey = config.get("translate_hotkey", "alt+t")
            self.assistant_hotkey = config.get("assistant_hotkey", "alt+g")
            self.stop_overlay_hotkey = config.get("stop_overlay_hotkey", "alt+x")
            self.overlay_position = config.get("overlay_position")
            self.window_geometry = config.get("window_geometry") or self.window_geometry
            self.response_geometry = (
                config.get("response_geometry") or self.response_geometry
            )
            self.auto_start_gemma = bool(config.get("auto_start_gemma", False))
            self.gemma_backend = config.get("gemma_backend", "cpu")
            if config.get("gemma_model") == "gemma4-e2b":
                self.gemma_backend = config.get("gemma_backend", "cpu")
            self.default_ocr_engine = config.get("default_ocr_engine", "oneocr")
            provider = normalize_translation_provider(
                config.get("translation_provider") or "argos"
            )
            if provider == "argos" and bool(config.get("auto_start_gemma", False)):
                provider = "argos_gemma"
            self.translation_provider = provider
            set_preferred_backend(self.gemma_backend)
            legacy_overlay = config.get("overlay_mode")
            if legacy_overlay not in ("layer", "over"):
                legacy_overlay = None

            # Migración desde config antigua (sin sesiones)
            if "sessions" not in config:
                session = default_session()
                session["translator_region"] = config.get("translator_region")
                session["journal_region"] = config.get("journal_region")
                session["guide_path"] = config.get("guide_path", "")
                if legacy_overlay:
                    session["overlay_mode"] = legacy_overlay
                self.sessions = [session]
                self.active_session_id = session["id"]
                self.save_config()
                return

            self.sessions = config.get("sessions") or [default_session()]
            self.active_session_id = config.get("active_session_id")
            if not any(s["id"] == self.active_session_id for s in self.sessions):
                self.active_session_id = self.sessions[0]["id"]
            for s in self.sessions:
                if not s.get("overlay_mode"):
                    s["overlay_mode"] = legacy_overlay or "layer"
                if not s.get("ocr_engine"):
                    s["ocr_engine"] = self.default_ocr_engine or "oneocr"

            # Migrar config legado (cwd) → junto al exe/script
            if os.path.abspath(config_path) != os.path.abspath(CONFIG_FILE):
                self.save_config()

        except Exception as e:
            print(f"Error al cargar configuración: {e}")
            session = default_session()
            self.sessions = [session]
            self.active_session_id = session["id"]

    def consult_ollama(self, query_text, force_auto=False):
        self.consult_guide(query_text, force_auto=force_auto)

    def consult_guide(self, query_text, force_auto=False):
        self.update_status("Consultando guía (Gemma)…", "yellow")
        lang = (
            self.active_session.get("assistant_language", "es")
            if self.active_session
            else "es"
        )
        warn_full = (
            self._parse_section_selection() == "full" and is_long_guide(self.guide_text)
        )

        def worker():
            try:
                context, resolve_err = self._resolve_guide_context(
                    query_text, force_auto=force_auto
                )
                if resolve_err:
                    self.after(0, lambda m=resolve_err: self._on_section_resolve_error(m))
                    return

                result = self.guide_assistant.query_guide(
                    guide_text=context,
                    query_text=query_text,
                    response_language=lang,
                )
                print(f"\nConsulta: {query_text}")
                print(f"Resultado guía ok={result.get('ok')} steps={result.get('steps')!r}")

                self.after(
                    0,
                    lambda: self._show_assistant_response(
                        query_text,
                        result,
                        warned_full=warn_full,
                    ),
                )
            except Exception as e:
                error_msg = f"Error al consultar guía: {str(e)}"
                print(error_msg)
                self.after(0, lambda m=error_msg: self.update_status(m, "red"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_section_resolve_error(self, msg):
        self.update_status(msg, "orange")
        messagebox.showwarning("Sección", msg)

    def _continue_from_assistant(self, source_sentence, display_sentence=None):
        """Continuar anclando en la oración ORIGINAL de la guía (consulta interna)."""
        source = (source_sentence or "").strip()
        display = (display_sentence or source).strip()
        if not source and not display:
            messagebox.showwarning("Continuar", "No hay oración para continuar.")
            return

        # No tocar el campo de pregunta: la continuación es interna
        from .proper_nouns import polish_spanish_guide

        shown = polish_spanish_guide(display or source, source or "")
        query_label = f"(continuación) {shown}"

        self.update_status("Continuando desde la guía (oración original)…", "yellow")
        lang = (
            self.active_session.get("assistant_language", "es")
            if self.active_session
            else "es"
        )
        anchor = source or display

        def worker():
            try:
                result = self.guide_assistant.continue_from_anchor(
                    self.guide_text,
                    anchor,
                    response_language=lang,
                )
                self.after(
                    0,
                    lambda: self._show_assistant_response(query_label, result),
                )
            except Exception as e:
                msg = f"Error al continuar: {e}"
                self.after(0, lambda m=msg: self.update_status(m, "red"))

        threading.Thread(target=worker, daemon=True).start()

    def _show_assistant_response(self, query_text, result, warned_full=False):
        if isinstance(result, str):
            AssistantResponseWindow(
                self,
                query_text,
                result,
                source_text=None,
                on_continue=self._continue_from_assistant,
                continue_source=None,
                felipe_text=None,
            )
            self.update_status("Consulta completada", "lime")
            return

        steps = result.get("steps") or ""
        source = result.get("source")
        continue_source = result.get("continue_anchor")
        felipe = result.get("felipe")
        if result.get("error"):
            self.update_status(result["error"], "red")
            messagebox.showerror("Gemma / Guía", result["error"])
            return

        AssistantResponseWindow(
            self,
            query_text,
            steps,
            source_text=source,
            on_continue=self._continue_from_assistant,
            continue_source=continue_source,
            felipe_text=felipe,
        )
        status = "Consulta completada"
        if warned_full:
            status += " (usaste toda la guía: menos fiable)"
        if not result.get("ok"):
            status = "Sin respaldo en la guía (no se inventó tip)"
            self.update_status(status, "orange")
        else:
            self.update_status(status, "lime")

    def translate_and_show(self, blocks_or_text):
        provider = getattr(self.translator, "provider", "gemma")
        label = TRANSLATION_PROVIDERS.get(provider, provider)
        self.update_status(f"Traduciendo ({label})…", "yellow")
        src = self.translator.source
        tgt = self.translator.target

        # Compat: string plano (tests / llamadas viejas) → un bloque
        if isinstance(blocks_or_text, str):
            from .ocr_engine import TextBlock

            blocks = [TextBlock(text=blocks_or_text, x=0, y=0, w=0, h=0, label="Texto")]
        else:
            blocks = list(blocks_or_text or [])

        staged = provider == "argos_gemma"

        def worker():
            try:
                if staged:
                    draft = self.translator.translate_blocks(blocks, review=False)
                    self.after(
                        0,
                        lambda r=draft, s=src, g=tgt: self._show_translation(
                            r, s, g, refining=True
                        ),
                    )
                    from .gemma_translate import is_server_running
                    from .review_translate import review_block_results

                    if not is_server_running():
                        self.after(
                            0,
                            lambda: self.update_status(
                                "Borrador Argos (Gemma apagado — sin refinado)",
                                "orange",
                            ),
                        )
                        return
                    self.after(
                        0,
                        lambda: self.update_status(
                            "Refinando con Gemma…", "yellow"
                        ),
                    )
                    reviewed = review_block_results(
                        draft, src, tgt, timeout=35.0
                    )
                    results = reviewed
                else:
                    results = self.translator.translate_blocks(blocks)
                print(
                    "Traducción bloques:\n"
                    + "\n---\n".join(
                        f"[{r.get('label')}] {r.get('translated')}" for r in results
                    )
                )
                self.after(
                    0,
                    lambda r=results, s=src, g=tgt: self._show_translation(
                        r, s, g, refining=False
                    ),
                )
            except Exception as e:
                error_msg = f"Error en traducción: {str(e)}"
                print(error_msg)
                self.after(0, lambda m=error_msg: self.update_status(m, "red"))

        threading.Thread(target=worker, daemon=True).start()

    def _show_translation(self, results, src, tgt, *, refining=False):
        if isinstance(results, str):
            sections = [("Traducción", results, "")]
            is_err = results.startswith("[Error:")
            results_list = [
                {"label": "Traducción", "translated": results, "source_text": "", "x": 0, "y": 0, "w": 0, "h": 0}
            ]
        else:
            results_list = list(results or [])
            sections = [
                (
                    r.get("label") or "Texto",
                    r.get("translated") or "",
                    r.get("source_text") or "",
                )
                for r in results_list
            ]
            is_err = any(
                (r.get("translated") or "").startswith("[Error:") for r in results_list
            )

        mode = getattr(self, "overlay_mode", "layer") or "layer"

        if not refining:
            if mode == "over":
                prev_over = getattr(self, "_over_overlay", None)
                if prev_over is not None and not is_err:
                    prev_over.update_results(results_list)
                    self.update_status(
                        f"Over: {len(sections)} bloque(s) (refinado)", "lime"
                    )
                    return
            else:
                prev_layer = getattr(self, "_layer_overlay", None)
                if prev_layer is not None and not is_err:
                    prev_layer.update_sections(sections)
                    self.update_status(
                        f"Layer: {len(sections)} bloque(s) (refinado)", "lime"
                    )
                    return

        if mode == "over" and self.translator_region:
            from .ocr_engine import UPSCALE

            TranslatorOverlayOver(
                self,
                results=results_list,
                region=self.translator_region,
                zoom=float(UPSCALE),
                auto_close_ms=0,
            )
        else:
            prev = getattr(self, "_layer_overlay", None)
            if prev is not None and not refining:
                try:
                    prev.destroy()
                except Exception:
                    pass
            self._layer_overlay = TranslatorOverlay(
                self,
                sections=sections,
                source_label=TRANSLATOR_LANGUAGES.get(src, src),
                target_label=TRANSLATOR_LANGUAGES.get(tgt, tgt),
                position=self.overlay_position,
                on_position_changed=self.on_overlay_position_changed,
                auto_close_ms=0 if (is_err or refining) else 20000,
                show_ocr=True,
            )
            if refining:
                self._layer_overlay.set_refining(True)
        if is_err:
            self.update_status("Traducción con errores (ver overlay)", "red")
        elif refining:
            self.update_status("Borrador Argos · refinando con Gemma…", "yellow")
        else:
            tag = "Over" if mode == "over" else "Layer"
            self.update_status(f"{tag}: {len(sections)} bloque(s)", "lime")
    def _on_main_configure(self, event=None):
        if event is not None and event.widget is not self:
            return
        # Debounce: no spamear disco en cada pixel de resize
        if getattr(self, "_geom_save_after_id", None):
            try:
                self.after_cancel(self._geom_save_after_id)
            except Exception:
                pass

        def _persist():
            try:
                self.window_geometry = self.geometry()
            except Exception:
                return
            self._geom_save_after_id = None

        self._geom_save_after_id = self.after(400, _persist)

    def _startup_local_models(self):
        """Al abrir: inicia Gemma si el usuario lo pidió."""
        if not self.auto_start_gemma:
            return
        self.update_status("Iniciando Gemma…", "yellow")

        def worker():
            notes = []
            try:
                if self.litert_manager.is_running():
                    notes.append("Gemma OK")
                elif self.litert_manager.is_installed():
                    self.litert_manager.start_server(backend=self.gemma_backend)
                    notes.append("Gemma iniciado")
                else:
                    notes.append("Gemma: falta Setup")
            except Exception as e:
                notes.append(f"Gemma: {e}")
                print(f"Startup Gemma: {e}")

            summary = " · ".join(notes) if notes else "Sin cambios"
            color = "lime" if notes and "falta" not in summary else "orange"

            def done():
                self.update_status(f"Modelos: {summary}", color)
                self._refresh_gemma_status()

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _shutdown_local_models(self):
        """Al salir: libera RAM deteniendo Gemma/LiteRT."""
        try:
            self.litert_manager.stop_server()
        except Exception as e:
            print(f"Al cerrar LiteRT: {e}")

    def on_closing(self):
        try:
            self.window_geometry = self.geometry()
        except Exception:
            pass
        try:
            self.save_config()
        except Exception as e:
            print(f"Al guardar config al cerrar: {e}")
        try:
            self.capture_manager.stop_hotkeys()
        except Exception as e:
            print(f"Al detener hotkeys: {e}")
        self._shutdown_local_models()
        self.destroy()


if __name__ == "__main__":
    app = EstiloKaioApp()
    app.mainloop()
