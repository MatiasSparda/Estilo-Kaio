"""Motores OCR (OneOCR, EasyOCR, WinRT)."""

from .base import bbox_quad_to_rect
from .easyocr_backend import EasyOcrBackend
from .oneocr_backend import OneOcrBackend
from .winrt_backend import WinRtBackend

__all__ = [
    "bbox_quad_to_rect",
    "OneOcrBackend",
    "EasyOcrBackend",
    "WinRtBackend",
]
