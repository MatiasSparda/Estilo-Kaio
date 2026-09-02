"""Windows OCR (WinRT) — fallback. Carga perezosa: importar winrt rompe ORT de RapidOCR."""

from __future__ import annotations

import asyncio
import io
from typing import Any

from PIL import Image

from ..ocr_types import OcrLineBox, OCR_LANGUAGE_CANDIDATES

_winrt_loaded = False
_winrt_ok = False
OcrEngine = None
Language = None
BitmapDecoder = None
InMemoryRandomAccessStream = None
DataWriter = None


def ensure_winrt() -> bool:
    """Importa winrt solo cuando hace falta (nunca al importar el modulo)."""
    global _winrt_loaded, _winrt_ok
    global OcrEngine, Language, BitmapDecoder, InMemoryRandomAccessStream, DataWriter
    if _winrt_loaded:
        return _winrt_ok
    _winrt_loaded = True
    try:
        from winrt.windows.media.ocr import OcrEngine as _OcrEngine
        from winrt.windows.graphics.imaging import BitmapDecoder as _BitmapDecoder
        from winrt.windows.storage.streams import (
            InMemoryRandomAccessStream as _InMemoryRandomAccessStream,
            DataWriter as _DataWriter,
        )
        from winrt.windows.globalization import Language as _Language

        OcrEngine = _OcrEngine
        BitmapDecoder = _BitmapDecoder
        InMemoryRandomAccessStream = _InMemoryRandomAccessStream
        DataWriter = _DataWriter
        Language = _Language
        _winrt_ok = True
    except ImportError as e:
        print(f"WARNING: Windows OCR no disponible: {e}")
        _winrt_ok = False
    return _winrt_ok


def __getattr__(name: str):
    # Compat: `from ... import WINDOWS_OCR_AVAILABLE` sin cargar winrt.
    if name == "WINDOWS_OCR_AVAILABLE":
        return False
    raise AttributeError(name)


def _bbox_from_words(words: Any) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    rights: list[float] = []
    bottoms: list[float] = []
    for word in words or []:
        rect = getattr(word, "bounding_rect", None)
        if rect is None:
            continue
        left = float(getattr(rect, "x", getattr(rect, "left", 0)) or 0)
        top = float(getattr(rect, "y", getattr(rect, "top", 0)) or 0)
        width = float(getattr(rect, "width", 0) or 0)
        height = float(getattr(rect, "height", 0) or 0)
        xs.append(left)
        ys.append(top)
        rights.append(left + width)
        bottoms.append(top + height)
    if not xs:
        return None
    x0, y0 = min(xs), min(ys)
    x1, y1 = max(rights), max(bottoms)
    return x0, y0, max(1.0, x1 - x0), max(1.0, y1 - y0)


def _lines_from_result(result) -> list[OcrLineBox]:
    lines_out: list[OcrLineBox] = []
    for line in result.lines:
        text = (line.text or "").strip()
        if not text:
            continue
        bbox = _bbox_from_words(getattr(line, "words", None))
        if bbox is None:
            lines_out.append(
                OcrLineBox(text=text, x=0, y=float(len(lines_out) * 20), w=100, h=16)
            )
        else:
            x, y, w, h = bbox
            lines_out.append(OcrLineBox(text=text, x=x, y=y, w=w, h=h))
    return lines_out


class WinRtBackend:
    id = "winrt"

    def __init__(self, language_code: str = "en"):
        self.language_code = language_code
        self.ocr_engine = None
        self.active_ocr_tag = None
        self.last_error = None
        if ensure_winrt():
            self._init_engine(language_code)

    def available_language_tags(self) -> list[str]:
        if not ensure_winrt():
            return []
        try:
            return [lang.language_tag for lang in OcrEngine.available_recognizer_languages]
        except Exception as e:
            self.last_error = str(e)
            return []

    def _try_create_from_tag(self, tag: str):
        if not Language:
            return None
        try:
            return OcrEngine.try_create_from_language(Language(tag))
        except Exception:
            return None

    def _init_engine(self, language_code: str) -> None:
        self.ocr_engine = None
        self.active_ocr_tag = None
        self.last_error = None
        if not ensure_winrt():
            self.last_error = "winrt no instalado"
            return

        available = self.available_language_tags()
        for tag in OCR_LANGUAGE_CANDIDATES.get(language_code, [language_code]):
            engine = self._try_create_from_tag(tag)
            if engine:
                self.ocr_engine = engine
                self.active_ocr_tag = tag
                self.language_code = language_code
                return

        for tag in available:
            base = tag.split("-")[0].lower()
            wanted = language_code.split("-")[0].lower()
            if base == wanted or tag.lower().startswith(wanted):
                engine = self._try_create_from_tag(tag)
                if engine:
                    self.ocr_engine = engine
                    self.active_ocr_tag = tag
                    self.language_code = language_code
                    return

        try:
            self.ocr_engine = OcrEngine.try_create_from_user_profile_languages()
            if self.ocr_engine:
                self.active_ocr_tag = "user-profile"
                self.language_code = language_code
                return
        except Exception as e:
            self.last_error = str(e)

        for tag in available:
            engine = self._try_create_from_tag(tag)
            if engine:
                self.ocr_engine = engine
                self.active_ocr_tag = tag
                self.language_code = language_code
                return

        self.last_error = (
            "No hay packs OCR de Windows. Instalá el idioma en Configuración → Idioma."
        )

    def set_language(self, code: str) -> None:
        if code == self.language_code and self.ocr_engine:
            return
        if ensure_winrt():
            self._init_engine(code)

    def is_available(self) -> bool:
        return bool(self.ocr_engine)

    def has_exact_language_pack(self, language_code: str | None = None) -> bool:
        code = language_code or self.language_code
        available = [t.lower() for t in self.available_language_tags()]
        if not available:
            return False
        wanted = {code.split("-")[0].lower()}
        for tag in OCR_LANGUAGE_CANDIDATES.get(code, [code]):
            wanted.add(tag.lower().split("-")[0])
        return any(a.split("-")[0] in wanted for a in available)

    def status_message(self) -> str:
        if not ensure_winrt():
            return "WinRT: paquetes winrt no instalados"
        if not self.ocr_engine:
            return self.last_error or "WinRT: no disponible"
        packs = ", ".join(self.available_language_tags()) or "(ninguno)"
        if self.has_exact_language_pack(self.language_code):
            return f"WinRT listo ({self.active_ocr_tag}) · {packs}"
        return (
            f"WinRT fallback ({self.active_ocr_tag}) · pediste '{self.language_code}' · {packs}"
        )

    async def _recognize_async(self, image: Image.Image):
        if not self.ocr_engine:
            raise RuntimeError(self.last_error or "WinRT no disponible")

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        img_bytes = buf.getvalue()

        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(img_bytes)
        await writer.store_async()
        await writer.flush_async()
        stream.seek(0)

        decoder = await BitmapDecoder.create_async(stream)
        software_bitmap = await decoder.get_software_bitmap_async()
        return await self.ocr_engine.recognize_async(software_bitmap)

    def recognize_lines(self, image: Image.Image) -> list[OcrLineBox]:
        if not self.ocr_engine:
            return []
        try:
            result = asyncio.run(self._recognize_async(image))
            return _lines_from_result(result)
        except Exception as e:
            self.last_error = str(e)
            print(f"WinRT OCR error: {e}")
            return []
