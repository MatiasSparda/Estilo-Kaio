from __future__ import annotations

import tkinter.font as tkfont

import customtkinter as ctk

from .ocr_dic import correct_blocks, correct_ocr_text

# Idiomas del traductor OCR (códigos estables en la UI)
TRANSLATOR_LANGUAGES = {
    "en": "Inglés",
    "es": "Español",
    "ja": "Japonés",
    "ko": "Coreano",
    "zh-CN": "Chino (Simplificado)",
    "zh-TW": "Chino (Tradicional)",
    "pt": "Portugués",
    "fr": "Francés",
    "de": "Alemán",
    "it": "Italiano",
    "ru": "Ruso",
    "ar": "Árabe",
}


class TranslatorOverlay(ctk.CTkToplevel):
    """Overlay Layer: grande, tipografía grande, OCR + traducción."""

    MIN_W = 720
    MIN_H = 420

    def __init__(
        self,
        parent,
        translated_text=None,
        source_label="",
        target_label="",
        position=None,
        on_position_changed=None,
        auto_close_ms=20000,
        sections=None,
        show_ocr=True,
    ):
        super().__init__(parent)

        self.on_position_changed = on_position_changed
        self._drag_offset = None
        self._close_after_id = None
        self._translation_labels: list[ctk.CTkLabel] = []
        self._title_label: ctk.CTkLabel | None = None
        self._base_title = ""

        self.attributes("-topmost", True)
        self.overrideredirect(True)
        self.attributes("-alpha", 0.94)

        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        if sections:
            sec_list = []
            for item in sections:
                if len(item) >= 3:
                    t, c, ocr = item[0], item[1], item[2]
                else:
                    t, c, ocr = item[0], item[1], ""
                if (c or "").strip() or (ocr or "").strip():
                    sec_list.append((t, c or "", ocr or ""))
        elif translated_text:
            sec_list = [("Traducción", translated_text, "")]
        else:
            sec_list = [("Traducción", "", "")]

        body_chars = sum(len(c) + len(o) for _, c, o in sec_list)
        window_width = min(max(self.MIN_W, 900), int(screen_width * 0.78))
        est_h = 100 + len(sec_list) * 80 + body_chars // 3
        window_height = max(self.MIN_H, min(int(screen_height * 0.72), max(est_h, 480)))

        if position and "x" in position and "y" in position:
            x = int(position["x"])
            y = int(position["y"])
        else:
            x = (screen_width - window_width) // 2
            y = screen_height - window_height - 60

        x = max(0, min(x, screen_width - 120))
        y = max(0, min(y, screen_height - 80))

        self.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.configure(fg_color="#0d0d14")

        border_frame = ctk.CTkFrame(self, fg_color="#3d5afe", corner_radius=4)
        border_frame.pack(fill="both", expand=True, padx=2, pady=2)

        content_frame = ctk.CTkFrame(border_frame, fg_color="#12121c", corner_radius=2)
        content_frame.pack(fill="both", expand=True, padx=2, pady=2)

        header_frame = ctk.CTkFrame(content_frame, fg_color="#1a1a28", corner_radius=0, height=44)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)

        title = "Estilo Kaio · arrastra"
        if source_label and target_label:
            title = f"{source_label} → {target_label}  ·  arrastra / ESC cierra"
        self._base_title = title

        title_label = ctk.CTkLabel(
            header_frame,
            text=title,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#90caf9",
            cursor="fleur",
        )
        title_label.pack(side="left", padx=14, pady=8)
        self._title_label = title_label

        close_btn = ctk.CTkButton(
            header_frame,
            text="✕",
            width=36,
            height=30,
            command=self.destroy,
            fg_color="#c62828",
            hover_color="#b71c1c",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        close_btn.pack(side="right", padx=10, pady=6)

        scroll = ctk.CTkScrollableFrame(content_frame, fg_color="#12121c")
        scroll.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        wrap = window_width - 64
        for i, (sec_title, sec_text, ocr_src) in enumerate(sec_list):
            if i > 0:
                ctk.CTkFrame(scroll, fg_color="#2a2a3d", height=2).pack(
                    fill="x", pady=(16, 16)
                )
            ctk.CTkLabel(
                scroll,
                text=sec_title.upper(),
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#7e88a8",
                anchor="w",
            ).pack(fill="x", padx=6, pady=(0, 4))

            body_label = ctk.CTkLabel(
                scroll,
                text=sec_text or "—",
                font=ctk.CTkFont(size=22),
                text_color="#f5f5f7",
                wraplength=wrap,
                justify="left",
                anchor="w",
            )
            body_label.pack(fill="x", padx=6, pady=(0, 8))
            self._translation_labels.append(body_label)

            if show_ocr and (ocr_src or "").strip():
                ctk.CTkLabel(
                    scroll,
                    text=f"OCR : {ocr_src.strip()}",
                    font=ctk.CTkFont(size=13),
                    text_color="#6b7390",
                    wraplength=wrap,
                    justify="left",
                    anchor="w",
                ).pack(fill="x", padx=6, pady=(0, 4))

        for widget in (header_frame, title_label):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)
            widget.bind("<ButtonRelease-1>", self._end_drag)

        self.bind("<Escape>", lambda e: self.destroy())

        if auto_close_ms and auto_close_ms > 0:
            self._close_after_id = self.after(auto_close_ms, self.destroy)

        self.focus_force()

    def set_refining(self, refining: bool) -> None:
        if self._title_label is None:
            return
        suffix = "  ·  refinando…" if refining else ""
        self._title_label.configure(text=f"{self._base_title}{suffix}")

    def update_sections(self, sections) -> None:
        texts: list[str] = []
        for item in sections or []:
            if len(item) >= 2:
                texts.append((item[1] or "").strip() or "—")
        for idx, label in enumerate(self._translation_labels):
            if idx < len(texts):
                label.configure(text=texts[idx])
        self.set_refining(False)

    def _cancel_autoclose(self):
        if self._close_after_id is not None:
            try:
                self.after_cancel(self._close_after_id)
            except Exception:
                pass
            self._close_after_id = None

    def _start_drag(self, event):
        self._cancel_autoclose()
        self._drag_offset = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _on_drag(self, event):
        if not self._drag_offset:
            return
        x = event.x_root - self._drag_offset[0]
        y = event.y_root - self._drag_offset[1]
        self.geometry(f"+{x}+{y}")

    def _end_drag(self, event):
        self._drag_offset = None
        pos = {"x": self.winfo_x(), "y": self.winfo_y()}
        if self.on_position_changed:
            self.on_position_changed(pos)


class TranslatorOverlayOver:
    """
    Overlay Over: ventana(s) sobre el juego, ajustadas al texto traducido.
    Sin scroll: el tamaño se calcula con métricas de fuente + ajuste fino al render.
    Solo se cierra con Alt+X (o ESC / click derecho). Sin auto-cierre.
    """

    def __init__(
        self,
        parent,
        results,
        region,
        zoom=3.0,
        auto_close_ms=0,
    ):
        self._parent = parent
        self._windows: list[ctk.CTkToplevel] = []
        self._close_after_id = None
        self._primary_label: ctk.CTkLabel | None = None
        self._primary_win: ctk.CTkToplevel | None = None
        self._primary_layout: dict | None = None

        prev = getattr(parent, "_over_overlay", None)
        if prev is not None:
            try:
                prev.destroy()
            except Exception:
                pass
        parent._over_overlay = self

        region = region or {}
        rx = int(region.get("x") or 0)
        ry = int(region.get("y") or 0)
        rw = max(1, int(region.get("width") or 400))
        rh = max(1, int(region.get("height") or 200))
        zoom = max(1.0, float(zoom or 3.0))

        screen_w = parent.winfo_screenwidth()
        screen_h = parent.winfo_screenheight()

        items = [
            r
            for r in (results or [])
            if isinstance(r, dict)
            and (r.get("translated") or "").strip()
            and not (r.get("translated") or "").strip().startswith("[Error:")
            and not self._skip_overlay_item(r)
        ]
        if not items:
            return

        primary = self._pick_primary(items)

        self._open_overlay(
            parent,
            primary,
            rx,
            ry,
            rw,
            rh,
            zoom,
            screen_w,
            screen_h,
            merge_region=True,
        )

        if self._windows:
            self._windows[0].focus_force()
            # Sin auto-cierre: solo Alt+X / ESC / click derecho

    @staticmethod
    def _skip_overlay_item(r: dict) -> bool:
        label = (r.get("label") or "").strip()
        if label.startswith("Título"):
            return True
        src = (r.get("source_text") or "").strip()
        if src.isupper() and len(src.split()) == 1 and len(src) <= 12:
            return True
        return False

    @staticmethod
    def _pick_primary(items: list[dict]) -> dict:
        for r in items:
            if (r.get("label") or "").startswith("Diálogo"):
                return r
        return max(
            items,
            key=lambda r: len((r.get("translated") or "")),
        )

    @staticmethod
    def _map_bbox(r, rx, ry, rw, rh, img_w, img_h) -> tuple[int, int, int, int]:
        bx = float(r.get("x") or 0)
        by = float(r.get("y") or 0)
        bw = max(1.0, float(r.get("w") or 1))
        bh = max(1.0, float(r.get("h") or 1))
        img_w = max(float(img_w or 0), 1.0)
        img_h = max(float(img_h or 0), 1.0)
        sx = int(rx + (bx / img_w) * rw)
        sy = int(ry + (by / img_h) * rh)
        sw = max(1, int((bw / img_w) * rw))
        sh = max(1, int((bh / img_h) * rh))
        return sx, sy, sw, sh

    @staticmethod
    def _wrap_lines(font: tkfont.Font, paragraph: str, max_px: int) -> list[str]:
        words = (paragraph or "").split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if font.measure(trial) <= max_px:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    @staticmethod
    def _fit_text_geometry(
        text: str,
        sx: int,
        sy: int,
        wrap_w: int,
        src_block_h: int,
        src_line_count: int,
        screen_w: int,
        screen_h: int,
    ) -> tuple[int, int, int, int, int]:
        """Ventana justo al texto traducido (sin scroll)."""
        pad_x, pad_y = 14, 10
        wrap_w = max(100, min(int(wrap_w), screen_w - 16))
        inner_w = max(72, wrap_w - pad_x * 2)

        src_lines = max(1, src_line_count)
        if src_block_h >= 16:
            font_px = max(12, min(26, int(src_block_h / src_lines * 0.88)))
        else:
            font_px = max(12, min(22, int(inner_w / 26)))

        font = tkfont.Font(family="Segoe UI", size=font_px)
        all_lines: list[str] = []
        for para in (text or "").split("\n"):
            if para.strip():
                all_lines.extend(TranslatorOverlayOver._wrap_lines(font, para, inner_w))
            else:
                all_lines.append("")

        def _dims(f: tkfont.Font, lines: list[str]) -> tuple[int, int]:
            line_h = f.metrics("linespace")
            text_h = max(line_h, len(lines) * line_h)
            text_w = max((f.measure(ln) for ln in lines if ln), default=inner_w // 2)
            return text_w, text_h

        text_w, text_h = _dims(font, all_lines)
        win_w = min(wrap_w, max(100, text_w + pad_x * 2))
        win_h = text_h + pad_y * 2

        # Si no entra en pantalla, bajar fuente y reenvolver
        for _ in range(8):
            if sy + win_h <= screen_h - 4 and win_h <= int(screen_h * 0.92):
                break
            if font_px <= 11:
                break
            font_px -= 1
            font.configure(size=font_px)
            all_lines = []
            for para in (text or "").split("\n"):
                if para.strip():
                    all_lines.extend(
                        TranslatorOverlayOver._wrap_lines(font, para, inner_w)
                    )
                else:
                    all_lines.append("")
            text_w, text_h = _dims(font, all_lines)
            win_w = min(wrap_w, max(100, text_w + pad_x * 2))
            win_h = text_h + pad_y * 2

        sx = max(0, min(sx, screen_w - win_w))
        sy = max(0, min(sy, screen_h - win_h))
        win_w = min(win_w, screen_w - sx)
        win_h = min(win_h, screen_h - sy)
        return sx, sy, win_w, win_h, font_px

    def _overlay_geometry(
        self,
        r: dict,
        text: str,
        rx: int,
        ry: int,
        rw: int,
        rh: int,
        merge_region: bool,
        screen_w: int,
        screen_h: int,
    ) -> tuple[int, int, int, int, int]:
        img_w = float(r.get("img_w") or 0) or float(rw * 3)
        img_h = float(r.get("img_h") or 0) or float(rh * 3)
        sx, sy, sw, sh = self._map_bbox(r, rx, ry, rw, rh, img_w, img_h)

        src_text = (r.get("source_text") or "").strip()
        src_line_count = max(1, src_text.count("\n") + 1 if src_text else text.count("\n") + 1)

        # Ancho de envoltura: caja OCR; si es muy chica, usar ancho de región
        wrap_w = sw if sw >= rw * 0.28 else rw
        if merge_region and wrap_w < rw * 0.5:
            wrap_w = rw
            sx = rx

        return self._fit_text_geometry(
            text,
            sx,
            sy,
            wrap_w,
            sh,
            src_line_count,
            screen_w,
            screen_h,
        )

    def _open_overlay(
        self,
        parent,
        r: dict,
        rx,
        ry,
        rw,
        rh,
        zoom,
        screen_w,
        screen_h,
        merge_region: bool,
    ):
        text = (r.get("translated") or "").strip()
        sx, sy, sw, sh, font_px = self._overlay_geometry(
            r, text, rx, ry, rw, rh, merge_region, screen_w, screen_h
        )

        win = ctk.CTkToplevel(parent)
        win.attributes("-topmost", True)
        win.overrideredirect(True)
        win.attributes("-alpha", 0.92)
        win.geometry(f"{sw}x{sh}+{sx}+{sy}")
        win.configure(fg_color="#12121c")

        border = ctk.CTkFrame(win, fg_color="#3d5afe", corner_radius=4)
        border.pack(fill="both", expand=True, padx=1, pady=1)
        inner = ctk.CTkFrame(border, fg_color="#12121c", corner_radius=3)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        wrap_inner = max(72, sw - 28)
        label = ctk.CTkLabel(
            inner,
            text=text,
            font=ctk.CTkFont(size=font_px),
            text_color="#f5f5f7",
            wraplength=wrap_inner,
            justify="left",
            anchor="nw",
        )
        label.pack(padx=8, pady=6)
        if merge_region:
            self._primary_label = label
            self._primary_win = win
            self._primary_layout = {
                "r": r,
                "rx": rx,
                "ry": ry,
                "rw": rw,
                "rh": rh,
                "zoom": zoom,
                "screen_w": screen_w,
                "screen_h": screen_h,
            }

        # Ajuste fino al tamaño real renderizado (sin scroll)
        win.update_idletasks()
        req_h = label.winfo_reqheight() + 16
        req_w = max(sw, label.winfo_reqwidth() + 16)
        req_w = min(req_w, screen_w - sx)
        req_h = min(req_h, screen_h - sy)
        if req_h > 0 and req_w > 0:
            win.geometry(f"{req_w}x{req_h}+{sx}+{sy}")

        win.bind("<Escape>", lambda e, s=self: s.destroy())
        win.bind("<ButtonPress-3>", lambda e, s=self: s.destroy())
        self._windows.append(win)

    def update_results(self, results) -> None:
        items = [
            r
            for r in (results or [])
            if isinstance(r, dict)
            and (r.get("translated") or "").strip()
            and not (r.get("translated") or "").strip().startswith("[Error:")
            and not self._skip_overlay_item(r)
        ]
        if not items or self._primary_label is None or self._primary_win is None:
            return
        primary = self._pick_primary(items)
        text = (primary.get("translated") or "").strip()
        layout = self._primary_layout or {}
        r = layout.get("r") or primary
        sx, sy, sw, sh, font_px = self._overlay_geometry(
            r,
            text,
            layout.get("rx", 0),
            layout.get("ry", 0),
            layout.get("rw", 400),
            layout.get("rh", 200),
            True,
            layout.get("screen_w", self._parent.winfo_screenwidth()),
            layout.get("screen_h", self._parent.winfo_screenheight()),
        )
        wrap_inner = max(72, sw - 28)
        self._primary_label.configure(
            text=text,
            font=ctk.CTkFont(size=font_px),
            wraplength=wrap_inner,
        )
        win = self._primary_win
        win.update_idletasks()
        req_h = self._primary_label.winfo_reqheight() + 16
        req_w = max(sw, self._primary_label.winfo_reqwidth() + 16)
        req_w = min(req_w, layout.get("screen_w", win.winfo_screenwidth()) - sx)
        req_h = min(req_h, layout.get("screen_h", win.winfo_screenheight()) - sy)
        if req_h > 0 and req_w > 0:
            win.geometry(f"{req_w}x{req_h}+{sx}+{sy}")

    def destroy(self):
        if self._close_after_id is not None:
            try:
                self._parent.after_cancel(self._close_after_id)
            except Exception:
                pass
            self._close_after_id = None
        for win in list(self._windows):
            try:
                win.destroy()
            except Exception:
                pass
        self._windows.clear()
        if getattr(self._parent, "_over_overlay", None) is self:
            self._parent._over_overlay = None


TRANSLATION_PROVIDERS = {
    "gemma": "Gemma (IA local) · ~15–40 s",
    "google": "Google Translate · ~1–3 s",
    "google_gemma": "Google + Gemma · ~5–15 s",
}

# Estimaciones orientativas por diálogo (GPU/CPU e internet varían).
TRANSLATION_PROVIDER_ETA = {
    "gemma": "~15–40 s",
    "google": "~1–3 s",
    "google_gemma": "~5–15 s",
}


class Translator:
    """OCR overlay: Gemma, Google, o híbrido Google+revisión Gemma."""

    def __init__(self, source="en", target="es", provider="gemma"):
        self.source = source
        self.target = target
        self.provider = provider if provider in TRANSLATION_PROVIDERS else "gemma"

    def set_languages(self, source, target):
        self.source = source
        self.target = target

    def set_provider(self, provider: str):
        self.provider = provider if provider in TRANSLATION_PROVIDERS else "gemma"

    def translate(self, text):
        try:
            if not text or not text.strip():
                return "[Sin texto para traducir]"
            text = correct_ocr_text(text)
            if self.provider == "google":
                from .google_translate import translate_text as gt_text

                return gt_text(text, self.source, self.target)
            if self.provider == "google_gemma":
                from .gemma_translate import is_server_running
                from .google_translate import translate_text_with_review

                if not is_server_running():
                    raise RuntimeError(
                        "Google + Gemma requiere Gemma iniciado. "
                        "Usá 'Iniciar' en Traductor."
                    )
                return translate_text_with_review(
                    text, self.source, self.target, timeout=35.0
                )
            from .gemma_translate import translate_text as gemma_text

            return gemma_text(text, self.source, self.target)
        except Exception as e:
            print(f"Error en traducción: {e}")
            return f"[Error: {str(e)}]"

    def translate_blocks(self, blocks, *, review: bool | None = None):
        """Traduce bloques. review=None usa el default del provider."""
        try:
            if not blocks:
                return []
            blocks = correct_blocks(blocks)
            if self.provider == "google":
                from .google_translate import translate_blocks as gt_blocks

                return gt_blocks(blocks, self.source, self.target, review=False)
            if self.provider == "google_gemma":
                from .gemma_translate import is_server_running
                from .google_translate import translate_blocks as gt_blocks

                do_review = True if review is None else bool(review)
                if do_review and not is_server_running():
                    raise RuntimeError(
                        "Google + Gemma requiere Gemma iniciado. "
                        "Usá 'Iniciar' en Traductor."
                    )
                return gt_blocks(
                    blocks,
                    self.source,
                    self.target,
                    review=do_review,
                    review_timeout=35.0,
                )
            from .gemma_translate import translate_blocks as gemma_blocks

            return gemma_blocks(blocks, self.source, self.target, timeout=35.0)
        except Exception as e:
            print(f"Error en traducción por bloques: {e}")
            return [
                {
                    "label": "Error",
                    "source_text": "",
                    "translated": f"[Error: {e}]",
                }
            ]
