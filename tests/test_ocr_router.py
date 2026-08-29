"""Tests router OCR."""

from app.ocr_engine import OCREngine, OcrLineBox, ENGINE_IDS


class _FakeBackend:
    def __init__(self, bid: str, available: bool, lines=None):
        self.id = bid
        self._available = available
        self._lines = lines or [OcrLineBox("hello", 0, 0, 50, 10)]

    def is_available(self):
        return self._available

    def status_message(self):
        return f"{self.id} ok"

    def set_language(self, code):
        pass

    def recognize_lines(self, image):
        return list(self._lines)


def test_set_engine_valid():
    eng = OCREngine("en", "winrt")
    eng.set_engine("easyocr")
    assert eng.engine_id == "easyocr"
    eng.set_engine("invalid")
    assert eng.engine_id == "easyocr"


def test_resolve_fallback_to_winrt():
    eng = OCREngine("en", "oneocr")
    eng._oneocr = _FakeBackend("oneocr", False)
    eng._rapidocr = _FakeBackend("rapidocr", False)
    eng._easyocr = _FakeBackend("easyocr", False)
    eng._winrt = _FakeBackend("winrt", True)
    b = eng.resolve_backend()
    assert b is not None
    assert b.id == "winrt"
    assert eng.last_used_backend_id == "winrt"


def test_engine_ids_complete():
    assert set(ENGINE_IDS) == {"oneocr", "easyocr", "winrt", "rapidocr"}


if __name__ == "__main__":
    test_set_engine_valid()
    test_resolve_fallback_to_winrt()
    test_engine_ids_complete()
    print("ALL TESTS PASSED")
