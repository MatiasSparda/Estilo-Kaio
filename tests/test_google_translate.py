"""Tests de motores de traducción (sin red: mocks)."""

from app.review_translate import review_block_results
from app.translator import (
    TRANSLATION_PROVIDER_ETA,
    TRANSLATION_PROVIDERS,
    Translator,
    normalize_translation_provider,
)


def test_translation_providers_defined():
    assert "argos" in TRANSLATION_PROVIDERS
    assert "argos_gemma" in TRANSLATION_PROVIDERS
    assert "gemma" in TRANSLATION_PROVIDERS
    assert "online" not in TRANSLATION_PROVIDERS
    for key, label in TRANSLATION_PROVIDERS.items():
        assert key in TRANSLATION_PROVIDER_ETA
        assert TRANSLATION_PROVIDER_ETA[key] in label


def test_provider_aliases():
    assert normalize_translation_provider("google") == "argos"
    assert normalize_translation_provider("google_gemma") == "argos_gemma"
    assert normalize_translation_provider("online_gemma") == "argos_gemma"
    assert normalize_translation_provider("invalid") == "argos"


def test_translator_set_provider():
    t = Translator(provider="argos")
    assert t.provider == "argos"
    t.set_provider("argos_gemma")
    assert t.provider == "argos_gemma"
    t.set_provider("gemma")
    assert t.provider == "gemma"
    t.set_provider("online")
    assert t.provider == "argos"
    t.set_provider("invalid")
    assert t.provider == "argos"


def test_argos_translate_subprocess_mocked():
    import app.argos_translate as at

    calls = []

    def fake_once(text, source, target):
        calls.append((text, source, target))
        return f"ES:{text}"

    orig = at._translate_once
    at._translate_once = fake_once
    try:
        assert at.translate_text("Hello", "en", "es") == "ES:Hello"
        assert calls == [("Hello", "en", "es")]
    finally:
        at._translate_once = orig


def test_hybrid_review_block_results():
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
        out = review_block_results(drafts, "en", "es")
        assert out[0]["translated"] == "¡Gracias a los Dioses!"
    finally:
        gemma.review_translation = orig


def test_translator_routes_to_argos():
    import app.argos_translate as at

    calls = []
    orig = at.translate_text

    def fake_at(text, source, target):
        calls.append((text, source, target))
        return "Hola offline"

    at.translate_text = fake_at
    try:
        t = Translator(source="en", target="es", provider="argos")
        assert t.translate("Hello") == "Hola offline"
        assert calls == [("Hello", "en", "es")]
    finally:
        at.translate_text = orig


def test_hybrid_requires_gemma():
    import app.gemma_translate as gemma

    orig = gemma.is_server_running
    gemma.is_server_running = lambda: False
    try:
        t = Translator(provider="argos_gemma")
        out = t.translate("Hello")
        assert out.startswith("[Error:")
        assert "Gemma" in out
    finally:
        gemma.is_server_running = orig


if __name__ == "__main__":
    test_translation_providers_defined()
    test_provider_aliases()
    test_translator_set_provider()
    test_argos_translate_subprocess_mocked()
    test_hybrid_review_block_results()
    test_translator_routes_to_argos()
    test_hybrid_requires_gemma()
    print("ALL TESTS PASSED")
