from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

    from ..ocr_types import OcrLineBox


def bbox_quad_to_rect(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x3: float,
    y3: float,
    x4: float,
    y4: float,
) -> tuple[float, float, float, float]:
    xs = (x1, x2, x3, x4)
    ys = (y1, y2, y3, y4)
    x0, y0 = min(xs), min(ys)
    x1r, y1r = max(xs), max(ys)
    return x0, y0, max(1.0, x1r - x0), max(1.0, y1r - y0)
