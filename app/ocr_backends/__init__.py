"""Motores OCR (carga perezosa — OneOCR no debe contaminar ORT de RapidOCR al importar)."""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "bbox_quad_to_rect",
    "OneOcrBackend",
    "EasyOcrBackend",
    "WinRtBackend",
    "RapidOcrBackend",
]

if TYPE_CHECKING:
    from .base import bbox_quad_to_rect
    from .easyocr_backend import EasyOcrBackend
    from .oneocr_backend import OneOcrBackend
    from .rapidocr_backend import RapidOcrBackend
    from .winrt_backend import WinRtBackend


def __getattr__(name: str):
    if name == "bbox_quad_to_rect":
        from .base import bbox_quad_to_rect as fn

        return fn
    if name == "EasyOcrBackend":
        from .easyocr_backend import EasyOcrBackend as cls

        return cls
    if name == "OneOcrBackend":
        from .oneocr_backend import OneOcrBackend as cls

        return cls
    if name == "RapidOcrBackend":
        from .rapidocr_backend import RapidOcrBackend as cls

        return cls
    if name == "WinRtBackend":
        from .winrt_backend import WinRtBackend as cls

        return cls
    raise AttributeError(name)
