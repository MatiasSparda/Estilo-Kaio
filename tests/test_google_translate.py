"""Tests del motor Google Translate (sin red: mocks)."""
from app.google_translate import translate_blocks, translate_text
from app.translator import (
    TRANSLATION_PROVIDER_ETA,
    TRANSLATION_PROVIDERS,
    Translator,
)


def test_translation_providers_defined():
    assert "gemma" in TRANSLATION_PROVIDERS
    assert "google" in TRANSLATION_PROVIDERS
    assert "google_gemma" in TRANSLATION_PROVIDERS
    for key, label in TRANSLATION_PROVIDERS.items():
        assert key in TRANSLATION_PROVIDER_ETA
        assert TRANSLATION_PROVIDER_ETA[key] in label


def test_translator_set_provider():
    t = Translator(provider="gemma")
    assert t.provider == "gemma"
    t.set_provider("google")
    assert t.provider == "google"
    t.set_provider("google_gemma")
    assert t.provider == "google_gemma"
    t.set_provider("invalid")
    assert t.provider == "gemma"


def test_google_translate_text_mocked():
    import app.google_translate as gt

    class FakeGT:
        def __init__(self, source, target):
            self.source = source
            self.target = target

        def translate(self, text):
            return f"ES:{text}"

    orig = gt.GoogleTranslator
    gt.GoogleTranslator = FakeGT
    try:
        assert translate_text("Hello", "en", "es") == "ES:Hello"
    finally:
        gt.GoogleTranslator = orig


def test_google_translate_blocks_mocked():
    import app.google_translate as gt

    class FakeGT:
        def __init__(self, source, target):
            pass

        def translate(self, text):
            return f"[{text}]"

    class Block:
        def __init__(self, text, label="Diálogo"):
            self.text = text
            self.label = label
            self.x = 1
            self.y = 2
            self.w = 3
            self.h = 4
            self.img_w = 100
            self.img_h = 50

    orig = gt.GoogleTranslator
    gt.GoogleTranslator = FakeGT
    try:
        out = translate_blocks([Block("Hi there")], "en", "es")
        assert len(out) == 1
        assert out[0]["translated"] == "[Hi there]"
        assert out[0]["source_text"] == "Hi there"
        assert out[0]["label"] == "Diálogo"
    finally:
        gt.GoogleTranslator = orig


def test_hybrid_review_block_results():
    import app.google_translate as gt
    import app.gemma_translate as gemma

    drafts = [
        {
            "label": "Diálogo",
            "source_text": "Thank the Gods!",
            "translated": "Gracias a Dios!",
        }
    ]

    def fake_review(source_text, draft, source, target, **kwargs):
        assert "Gods" in source_text
        return "¡Gracias a los Dioses!"

    orig = gemma.review_translation
    gemma.review_translation = fake_review
    try:
        out = gt.review_block_results(drafts, "en", "es")
        assert out[0]["translated"] == "¡Gracias a los Dioses!"
    finally:
        gemma.review_translation = orig


def test_translator_routes_to_google():
    import app.google_translate as gt

    calls = []
    orig = gt.translate_text

    def fake_gt(text, source, target):
        calls.append((text, source, target))
        return "Hola"

    gt.translate_text = fake_gt
    try:
        t = Translator(source="en", target="es", provider="google")
        assert t.translate("Hello") == "Hola"
        assert calls == [("Hello", "en", "es")]
    finally:
        gt.translate_text = orig


def test_hybrid_requires_gemma(monkeypatch_running=False):
    import app.gemma_translate as gemma

    orig = gemma.is_server_running
    gemma.is_server_running = lambda: False
    try:
        t = Translator(provider="google_gemma")
        out = t.translate("Hello")
        assert out.startswith("[Error:")
        assert "Gemma" in out
    finally:
        gemma.is_server_running = orig


if __name__ == "__main__":
    test_translation_providers_defined()
    test_translator_set_provider()
    test_google_translate_text_mocked()
    test_google_translate_blocks_mocked()
    test_hybrid_review_block_results()
    test_translator_routes_to_google()
    test_hybrid_requires_gemma()
    print("ALL TESTS PASSED")
