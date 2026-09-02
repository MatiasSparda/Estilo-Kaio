"""RapidOCR (Paddle ONNX) — mejor en texto de escena / UI que WinRT genérico."""

from __future__ import annotations

from PIL import Image

from ..ocr_types import OcrLineBox
from .base import bbox_quad_to_rect


class RapidOcrBackend:
    id = "rapidocr"

    def __init__(self, language_code: str = "en"):
        self.language_code = language_code
        self.last_error: str | None = None
        self._engine = None

    def _module_ok(self) -> bool:
        try:
            import rapidocr  # noqa: F401

            return True
        except ImportError:
            try:
                import rapidocr_onnxruntime  # noqa: F401

                return True
            except ImportError:
                return False

    def _ensure_engine(self) -> bool:
        if self._engine is not None:
            return True
        last: Exception | None = None
        for _ in range(2):
            try:
                # Forzar ORT de pip ANTES de RapidOCR: si OneOCR copio
                # app/DLL/onnxruntime.dll (Microsoft), Windows puede cargar
                # ese y romper onnxruntime_pybind11_state.
                import onnxruntime  # noqa: F401

                try:
                    from rapidocr import RapidOCR
                except ImportError:
                    from rapidocr_onnxruntime import RapidOCR

                self._engine = RapidOCR()
                self.last_error = None
                return True
            except Exception as e:
                last = e
                self._engine = None
        self.last_error = f"RapidOCR init: {last}"
        return False

    def set_language(self, code: str) -> None:
        self.language_code = code

    def is_available(self) -> bool:
        return self._module_ok()

    def status_message(self) -> str:
        if not self._module_ok():
            return "RapidOCR: no instalado (pip install rapidocr onnxruntime)"
        if self._ensure_engine():
            return "RapidOCR listo (ONNX, escena)"
        return self.last_error or "RapidOCR: error al iniciar"

    def recognize_lines(self, image: Image.Image) -> list[OcrLineBox]:
        if not self._ensure_engine():
            return []
        try:
            import numpy as np

            arr = np.array(image.convert("RGB"))
            raw = self._engine(arr)
        except Exception as e:
            self.last_error = str(e)
            print(f"RapidOCR error: {e}")
            return []
        return _lines_from_rapidocr(raw)


def _lines_from_rapidocr(raw) -> list[OcrLineBox]:
    out: list[OcrLineBox] = []
    txts = getattr(raw, "txts", None)
    boxes = getattr(raw, "boxes", None)
    if txts is not None:
        for i, text in enumerate(txts):
            text = (text or "").strip()
            if not text:
                continue
            box = boxes[i] if boxes is not None and i < len(boxes) else None
            x, y, w, h = _box_to_rect(box, len(out))
            out.append(OcrLineBox(text=text, x=x, y=y, w=w, h=h))
        return out

    rows = raw[0] if isinstance(raw, tuple) else raw
    for item in rows or []:
        if not item:
            continue
        box, text = item[0], (item[1] or "").strip()
        if not text:
            continue
        x, y, w, h = _box_to_rect(box, len(out))
        out.append(OcrLineBox(text=text, x=x, y=y, w=w, h=h))
    return out


def _box_to_rect(box, index: int) -> tuple[float, float, float, float]:
    if box is None:
        return 0.0, float(index * 20), 100.0, 16.0
    try:
        pts = list(box)
        if len(pts) >= 4 and hasattr(pts[0], "__len__"):
            xs = [float(p[0]) for p in pts[:4]]
            ys = [float(p[1]) for p in pts[:4]]
            return bbox_quad_to_rect(
                xs[0], ys[0], xs[1], ys[1], xs[2], ys[2], xs[3], ys[3]
            )
    except (TypeError, IndexError, ValueError):
        pass
    return 0.0, float(index * 20), 100.0, 16.0
