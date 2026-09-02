import threading
import sys
import time

import mss
from PIL import Image
import keyboard
from .ocr_engine import OCREngine

_HOTKEY_DEBOUNCE_S = 0.35


class ScreenCaptureManager:
    def __init__(self, app):
        self.app = app
        self.ocr_engine = OCREngine()
        self.sct = mss.mss()
        self.hotkeys_registered = False
        self.translate_hotkey = "alt+t"
        self.assistant_hotkey = "alt+g"
        self.stop_overlay_hotkey = "alt+x"
        self._busy = False
        self._global_hotkeys = None
        self._use_global_hotkeys = False
        self._keyboard_handles: list = []
        self._last_hotkey_at = 0.0

    def _mark_hotkey(self) -> bool:
        now = time.monotonic()
        if now - self._last_hotkey_at < _HOTKEY_DEBOUNCE_S:
            return False
        self._last_hotkey_at = now
        return True

    def _start_keyboard_hooks(self) -> None:
        """Fallback / respaldo cuando los globales no bastan (exe, sin admin)."""
        for handle in self._keyboard_handles:
            try:
                keyboard.remove_hotkey(handle)
            except Exception:
                pass
        self._keyboard_handles.clear()
        specs = (
            (self.translate_hotkey, self._on_translate_hotkey_raw),
            (self.assistant_hotkey, self._on_assistant_hotkey_raw),
            (self.stop_overlay_hotkey, self._on_stop_overlay_hotkey_raw),
        )
        for combo, cb in specs:
            handle = keyboard.add_hotkey(combo, cb, suppress=False)
            self._keyboard_handles.append(handle)

    def set_hotkeys(self, translate_hotkey, assistant_hotkey, stop_overlay_hotkey="alt+x"):
        """Actualiza y re-registra las hotkeys."""
        translate_hotkey = (translate_hotkey or "alt+t").strip().lower()
        assistant_hotkey = (assistant_hotkey or "alt+g").strip().lower()
        stop_overlay_hotkey = (stop_overlay_hotkey or "alt+x").strip().lower()
        changed = (
            translate_hotkey != self.translate_hotkey
            or assistant_hotkey != self.assistant_hotkey
            or stop_overlay_hotkey != self.stop_overlay_hotkey
        )
        self.translate_hotkey = translate_hotkey
        self.assistant_hotkey = assistant_hotkey
        self.stop_overlay_hotkey = stop_overlay_hotkey
        if self.hotkeys_registered and changed:
            self.stop_hotkeys()
            self.start_hotkeys()
        elif not self.hotkeys_registered:
            self.start_hotkeys()

    def start_hotkeys(self):
        if self.hotkeys_registered:
            return

        self._use_global_hotkeys = False
        self._global_hotkeys = None
        global_ok = False
        global_err = ""

        if sys.platform == "win32":
            try:
                from .global_hotkeys import try_register

                gh = try_register(
                    self.app,
                    [
                        (1, self.translate_hotkey, self._on_translate_hotkey_raw),
                        (2, self.assistant_hotkey, self._on_assistant_hotkey_raw),
                        (3, self.stop_overlay_hotkey, self._on_stop_overlay_hotkey_raw),
                    ],
                )
                if gh is not None:
                    self._global_hotkeys = gh
                    self._use_global_hotkeys = True
                    global_ok = True
            except Exception as e:
                global_err = str(e)
                print(f"Hotkeys globales fallaron: {e}")

        keyboard_ok = False
        keyboard_err = ""
        try:
            self._start_keyboard_hooks()
            keyboard_ok = True
        except Exception as e:
            keyboard_err = str(e)
            print(f"Hotkeys keyboard fallaron: {e}")

        if global_ok or keyboard_ok:
            self.hotkeys_registered = True
            if global_ok and keyboard_ok:
                mode = "globales + respaldo"
            elif global_ok:
                mode = "globales"
            else:
                mode = "fallback keyboard"
            self.app.update_status(
                f"Hotkeys ({mode}): {self.translate_hotkey.upper()} traducir · "
                f"{self.assistant_hotkey.upper()} guía · "
                f"{self.stop_overlay_hotkey.upper()} cerrar overlay",
                "lime",
            )
            return

        detail = global_err or keyboard_err or "motivo desconocido"
        self.app.update_status(
            f"Error al registrar hotkeys: {detail}. "
            f"Cerrá otras instancias de EstiloKaio e intentá de nuevo.",
            "red",
        )

    def stop_hotkeys(self):
        if self._global_hotkeys is not None:
            try:
                self._global_hotkeys.unregister_all()
            except Exception:
                pass
            self._global_hotkeys = None
        for handle in self._keyboard_handles:
            try:
                keyboard.remove_hotkey(handle)
            except Exception:
                pass
        self._keyboard_handles.clear()
        if self.hotkeys_registered:
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
        self.hotkeys_registered = False
        self._use_global_hotkeys = False

    def capture_region(self, region):
        if not region:
            return None

        monitor = {
            "left": region["x"],
            "top": region["y"],
            "width": region["width"],
            "height": region["height"],
        }

        screenshot = self.sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        return img

    def _on_translate_hotkey_raw(self):
        if not self._mark_hotkey():
            return
        try:
            self.app.after(0, self._on_translate_hotkey_ui)
        except Exception as e:
            print(f"Error al encolar traducción: {e}")

    def _on_translate_hotkey_ui(self):
        self.app.update_status("Atajo traducir detectado…", "yellow")
        self.on_translate_hotkey()

    def _on_assistant_hotkey_raw(self):
        if not self._mark_hotkey():
            return
        try:
            self.app.after(0, self.on_assistant_hotkey)
        except Exception as e:
            print(f"Error al encolar asistente: {e}")

    def _on_stop_overlay_hotkey_raw(self):
        if not self._mark_hotkey():
            return
        try:
            self.app.after(0, self.on_stop_overlay_hotkey)
        except Exception as e:
            print(f"Error al encolar cierre overlay: {e}")

    def on_stop_overlay_hotkey(self):
        print(f"\n[HOTKEY] {self.stop_overlay_hotkey} - Cerrar overlay...")
        if hasattr(self.app, "close_translation_overlays"):
            self.app.close_translation_overlays()

    def _finish_translate(self, blocks):
        if blocks and blocks[0].text.startswith(
            ("[OCR no disponible]", "[Error OCR")
        ):
            self.app.update_status(blocks[0].text, "red")
            return

        if blocks:
            if len(blocks) >= 8:
                self.app.update_status(
                    "Muchos textos; achicá la región si sale ruido",
                    "orange",
                )
            preview = blocks[0].text[:50] + (
                "..." if len(blocks[0].text) > 50 else ""
            )
            from .ocr_engine import ENGINE_LABELS

            eng = self.ocr_engine.last_used_backend_id or self.ocr_engine.engine_id
            eng_name = ENGINE_LABELS.get(eng, eng or "OCR")
            ocr_s = getattr(self.ocr_engine, "last_ocr_seconds", 0.0) or 0.0
            self.app.update_status(
                f"{eng_name} · {len(blocks)} bloque(s) · {ocr_s:.1f}s OCR: {preview}",
                "cyan",
            )
            print(
                f"[OCR] motor={self.ocr_engine.last_used_backend_id} "
                f"truncado={getattr(self.ocr_engine, 'last_ocr_truncated', False)}"
            )
            print(f"[OCR] texto=\n{getattr(self.ocr_engine, 'last_ocr_joined', '')}")
            if getattr(self.ocr_engine, "last_ocr_truncated", False):
                self.app.update_status(
                    f"OCR incompleto ({eng_name}) — cambiá a OneOCR o achicá la región al texto",
                    "orange",
                )
            print(
                "Bloques OCR:\n"
                + "\n---\n".join(f"[{b.label}] {b.text}" for b in blocks)
            )
            if hasattr(self.app, "translate_and_show"):
                self.app.translate_and_show(blocks)
        else:
            self.app.update_status("No se detectó texto en la región", "orange")

    def on_translate_hotkey(self):
        print(f"\n[HOTKEY] {self.translate_hotkey} - Iniciando traducción...")

        if self._busy:
            self.app.update_status("Ya hay una captura en curso…", "orange")
            return

        if not self.app.translator_region:
            self.app.update_status("Error: Región del traductor no definida", "red")
            print("Error: Región del traductor no definida")
            return

        # Cartel encima del juego → OCR mezcla ES+EN. Cerrar antes de grabar pantalla.
        if hasattr(self.app, "close_translation_overlays"):
            self.app.close_translation_overlays(silent=True)
            try:
                self.app.update_idletasks()
            except Exception:
                pass

        self._busy = True
        self.app.update_status("Capturando y leyendo OCR…", "yellow")
        region = dict(self.app.translator_region)

        def worker():
            try:
                img = self.capture_region(region)
                if not img:
                    self.app.after(
                        0,
                        lambda: self.app.update_status("Captura vacía", "red"),
                    )
                    return
                blocks = self.ocr_engine.extract_blocks(img)
                if self.ocr_engine.needs_language_pack():
                    self.app.after(
                        0,
                        lambda: self.app.update_status(
                            "Windows OCR sin pack del idioma — instalá OCR inglés en Windows",
                            "orange",
                        ),
                    )
                self.app.after(0, lambda b=blocks: self._finish_translate(b))
            except Exception as e:
                error_msg = f"Error en captura/OCR: {str(e)}"
                print(error_msg)
                self.app.after(0, lambda m=error_msg: self.app.update_status(m, "red"))
            finally:
                self._busy = False

        threading.Thread(target=worker, daemon=True).start()

    def on_assistant_hotkey(self):
        print(f"\n[HOTKEY] {self.assistant_hotkey} - Consultando asistente...")

        if self._busy:
            self.app.update_status("Ya hay una captura en curso…", "orange")
            return

        if not self.app.journal_region:
            self.app.update_status("Error: Región del diario no definida", "red")
            print("Error: Región del diario no definida")
            return

        if not self.app.guide_text:
            self.app.update_status("Error: No se ha cargado una guía", "red")
            print("Error: No se ha cargado una guía")
            return

        self._busy = True
        try:
            self.app.update_status("Capturando región del diario...", "yellow")
            img = self.capture_region(self.app.journal_region)

            if img:
                self.app.update_status("Extrayendo texto del diario con OCR...", "yellow")
                text = self.ocr_engine.extract_text(img)
                print(f"Texto del diario extraído: {text}")

                if text.startswith("[OCR no disponible]") or text.startswith("[Error OCR"):
                    self.app.update_status(text, "red")
                    return

                if text and text.strip():
                    preview = text[:50] + ("..." if len(text) > 50 else "")
                    self.app.update_status(f"Diario leído: {preview}", "cyan")
                    if hasattr(self.app, "consult_guide"):
                        self.app.consult_guide(text, force_auto=True)
                else:
                    self.app.update_status("No se detectó texto en el diario", "orange")

        except Exception as e:
            error_msg = f"Error en captura/OCR del diario: {str(e)}"
            self.app.update_status(error_msg, "red")
            print(error_msg)
        finally:
            self._busy = False
