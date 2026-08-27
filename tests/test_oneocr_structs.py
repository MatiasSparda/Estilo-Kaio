"""Structs OneOCR."""

from app.ocr_backends.base import bbox_quad_to_rect


def test_bbox_quad_to_rect():
    x, y, w, h = bbox_quad_to_rect(10, 20, 110, 20, 110, 40, 10, 40)
    assert x == 10
    assert y == 20
    assert w == 100
    assert h == 20


def test_oneocr_status():
    from app.ocr_backends.oneocr_backend import OneOcrBackend

    b = OneOcrBackend("en")
    msg = b.status_message()
    assert "OneOCR" in msg


if __name__ == "__main__":
    test_bbox_quad_to_rect()
    test_oneocr_status()
    print("ALL TESTS PASSED")
