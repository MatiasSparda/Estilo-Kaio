"""Tests de motores de traducción (sin red: mocks)."""

from app.review_translate import review_block_results
from app.translator import (
    TRANSLATION_PROVIDER_ETA,
    TRANSLATION_PROVIDERS,
    Translator,
    normalize_translation_provider,
)


def test_translation_providers_defined():
    assert "offline" in TRANSLATION_PROVIDERS
    assert "offline_gemma" in TRANSLATION_PROVIDERS
    assert "gemma" in TRANSLATION_PROVIDERS
    assert "argos" not in TRANSLATION_PROVIDERS
    assert "online" not in TRANSLATION_PROVIDERS
    for key, label in TRANSLATION_PROVIDERS.items():
        assert key in TRANSLATION_PROVIDER_ETA
        assert TRANSLATION_PROVIDER_ETA[key] in label


def test_provider_aliases():
    assert normalize_translation_provider("google") == "offline"
    assert normalize_translation_provider("argos") == "offline"
    assert normalize_translation_provider("argos_gemma") == "offline_gemma"
    assert normalize_translation_provider("google_gemma") == "offline_gemma"
    assert normalize_translation_provider("online_gemma") == "offline_gemma"
    assert normalize_translation_provider("invalid") == "offline"


def test_translator_set_provider():
    t = Translator(provider="offline")
    assert t.provider == "offline"
    t.set_provider("offline_gemma")
    assert t.provider == "offline_gemma"
    t.set_provider("gemma")
    assert t.provider == "gemma"
    t.set_provider("online")
    assert t.provider == "offline"
    t.set_provider("invalid")
    assert t.provider == "offline"


def test_offline_translate_subprocess_mocked():
    import app.offline_translate as ot

    calls = []

    def fake_once(text, source, target):
        calls.append((text, source, target))
        return f"ES:{text}"

    orig = ot._translate_once
    ot._translate_once = fake_once
    try:
        assert ot.translate_text("Hello", "en", "es") == "ES:Hello"
        assert calls == [("Hello", "en", "es")]
    finally:
        ot._translate_once = orig


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


def test_translator_routes_to_offline():
    import app.offline_translate as ot

    calls = []
    orig = ot.translate_text

    def fake_ot(text, source, target):
        calls.append((text, source, target))
        return "Hola offline"

    ot.translate_text = fake_ot
    try:
        t = Translator(source="en", target="es", provider="offline")
        assert t.translate("Hello") == "Hola offline"
        assert calls == [("Hello", "en", "es")]
    finally:
        ot.translate_text = orig


def test_hybrid_requires_gemma():
    import app.gemma_translate as gemma

    orig = gemma.is_server_running
    gemma.is_server_running = lambda: False
    try:
        t = Translator(provider="offline_gemma")
        out = t.translate("Hello")
        assert out.startswith("[Error:")
        assert "Gemma" in out
    finally:
        gemma.is_server_running = orig


if __name__ == "__main__":
    test_translation_providers_defined()
    test_provider_aliases()
    test_translator_set_provider()
    test_offline_translate_subprocess_mocked()
    test_hybrid_review_block_results()
    test_translator_routes_to_offline()
    test_hybrid_requires_gemma()
    print("ALL TESTS PASSED")
