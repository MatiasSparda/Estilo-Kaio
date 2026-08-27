"""QA de traducción: prompts generales y revisión por pares de idioma."""
from app.gemma_translate import (
    REASONING_REVIEW,
    REASONING_TRANSLATE,
    build_review_system_prompt,
    build_review_user_prompt,
    build_system_prompt,
    review_translation,
)


def test_both_passes_use_medium_thinking():
    assert REASONING_TRANSLATE == "medium"
    assert REASONING_REVIEW == "medium"


def test_system_prompt_uses_principles_not_word_patches():
    prompt = build_system_prompt("en", "es").lower()
    assert "singular/plural" in prompt or "singular" in prompt
    assert "in-world" in prompt or "in-world terminology" in prompt
    for word in ("cries", "gods", "llorando", "reflex action"):
        assert word not in prompt


def test_review_prompt_is_source_agnostic():
    prompt = build_review_system_prompt("en", "es").lower()
    assert "draft" in prompt
    assert "homograph" in prompt
    assert "singular/plural" in prompt
    for word in ("cries", "gods", "noa"):
        assert word not in prompt


def test_review_user_prompt_includes_both_texts():
    user = build_review_user_prompt(
        "Thank the Gods!",
        "Gracias a Dios!",
        "en",
        "es",
    )
    assert "Thank the Gods" in user
    assert "Gracias a Dios" in user


def test_review_translation_returns_draft_when_server_down(monkeypatch):
    monkeypatch.setattr("app.gemma_translate.is_server_running", lambda: False)
    draft = "Gracias a Dios"
    assert review_translation("Thank the Gods", draft, "en", "es") == draft
