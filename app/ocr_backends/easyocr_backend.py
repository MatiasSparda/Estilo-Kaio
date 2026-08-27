"""EasyOCR — alternativa instalable."""

from __future__ import annotations

from PIL import Image

from ..ocr_types import OcrLineBox
from .base import bbox_quad_to_rect

EASYOCR_LANG_MAP = {
    "en": "en",
    "es": "en",  # EasyOCR usa en para latino; lista sin es dedicado
    "ja": "ja",
    "ko": "ko",
    "zh-CN": "ch_sim",
    "zh-TW": "ch_tra",
    "pt": "en",
    "fr": "en",
    "de": "en",
    "it": "en",
    "ru": "en",
    "ar": "ar",
}


class EasyOcrBackend:
    id = "easyocr"

    def __init__(self, language_code: str = "en"):
        self.language_code = language_code
        self.last_error: str | None = None
        self._reader = None
        self._reader_lang: str | None = None

    def _easyocr_lang(self) -> str:
        return EASYOCR_LANG_MAP.get(self.language_code, "en")

    def _module_installed(self) -> bool:
        try:
            import easyocr  # noqa: F401

            return True
        except ImportError:
            return False

    def _ensure_reader(self) -> bool:
        if not self._module_installed():
            self.last_error = "EasyOCR no instalado — ejecutá Setup_EasyOCR.bat"
            return False
        lang = self._easyocr_lang()
        if self._reader is not None and self._reader_lang == lang:
            return True
        try:
            import easyocr

            self._reader = easyocr.Reader([lang], gpu=False, verbose=False)
            self._reader_lang = lang
            self.last_error = None
            return True
        except Exception as e:
            self.last_error = f"EasyOCR init: {e}"
            self._reader = None
            return False

    def set_language(self, code: str) -> None:
        if code != self.language_code:
            self.language_code = code
            self._reader = None
            self._reader_lang = None

    def is_available(self) -> bool:
        return self._module_installed()

    def status_message(self) -> str:
        if not self._module_installed():
            return "EasyOCR: no instalado (scripts/Setup_EasyOCR.bat)"
        if self._ensure_reader():
            return f"EasyOCR listo · idioma {self._reader_lang}"
        return self.last_error or "EasyOCR: error al iniciar"

    def recognize_lines(self, image: Image.Image) -> list[OcrLineBox]:
        if not self._ensure_reader():
            return []
        try:
            import numpy as np

            arr = np.array(image.convert("RGB"))
            results = self._reader.readtext(arr, detail=1, paragraph=False)
        except Exception as e:
            self.last_error = str(e)
            print(f"EasyOCR error: {e}")
            return []

        out: list[OcrLineBox] = []
        for item in results or []:
            if len(item) < 2:
                continue
            box, text = item[0], (item[1] or "").strip()
            if not text:
                continue
            if len(box) >= 4:
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                x, y, w, h = bbox_quad_to_rect(
                    xs[0], ys[0], xs[1], ys[1], xs[2], ys[2], xs[3], ys[3]
                )
            else:
                x, y, w, h = 0.0, float(len(out) * 20), 100.0, 16.0
            out.append(OcrLineBox(text=text, x=x, y=y, w=w, h=h))
        return out
