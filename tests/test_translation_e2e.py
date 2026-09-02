"""E2E traducción: OCR completo + pipeline con mocks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.ocr_engine import OCREngine, SENTENCE_END, ocr_looks_truncated
from app.translation_pipeline import (
    TranslationCallbacks,
    gemma_timeout_for,
    run_translation,
)

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ocr" / "tall_folk_dialog.png"


def test_rapidocr_pref_fallback_completes_sentence():
    """Con preferido rapidocr, fixture tall_folk debe terminar con .!?"""
    if not _FIXTURE.is_file():
        raise AssertionError(f"Falta fixture {_FIXTURE}")
    img = Image.open(_FIXTURE).convert("RGB")
    eng = OCREngine("en", "rapidocr")
    blocks = eng.extract_blocks(img)
    joined = eng.last_ocr_joined or " ".join(b.text for b in blocks)
    assert blocks, "sin bloques"
    assert not eng.last_ocr_truncated, f"OCR truncado: {joined!r}"
    last_line = joined.split("\n")[-1].strip()
    assert SENTENCE_END.search(last_line), f"sin cierre de frase: {last_line!r}"


def test_pipeline_offline_only_mocked():
    """run_translation offline llama on_final una vez."""
    fake = [{"label": "A", "translated": "Hola", "source_text": "Hi"}]

    with patch("app.offline_translate.translate_blocks", return_value=fake):
        finals: list = []
        run_translation(
            [{"text": "Hi"}],
            provider="offline",
            src="en",
            tgt="es",
            callbacks=TranslationCallbacks(on_final=finals.append),
        )
    assert finals == [fake]


def test_pipeline_gemma_error_keeps_draft_mocked():
    """on_draft llamado; on_gemma_error; on_final NO llamado."""
    draft = [{"label": "A", "translated": "Borrador", "source_text": "Hi"}]
    gemma_err = [{"label": "A", "translated": "[Error: timeout]", "source_text": "Hi"}]

    with (
        patch("app.offline_translate.translate_blocks", return_value=draft),
        patch("app.gemma_translate.is_server_running", return_value=True),
        patch("app.gemma_translate.translate_blocks", return_value=gemma_err),
    ):
        drafts: list = []
        finals: list = []
        errors: list = []

        run_translation(
            [{"text": "Hi"}],
            provider="offline_gemma",
            src="en",
            tgt="es",
            callbacks=TranslationCallbacks(
                on_draft=drafts.append,
                on_final=finals.append,
                on_gemma_error=errors.append,
            ),
        )
    assert drafts == [draft]
    assert errors and "timeout" in errors[0].lower()
    assert not finals


def test_gemma_timeout_scales_with_length():
    assert gemma_timeout_for("x" * 100) >= 90
    assert gemma_timeout_for("x" * 5000) > gemma_timeout_for("x" * 100)


def test_ocr_looks_truncated_helper():
    assert not ocr_looks_truncated("Hello world.\nGoodbye.")
    assert ocr_looks_truncated("Hello world.\nGoodbye with no punct")


if __name__ == "__main__":
    test_rapidocr_pref_fallback_completes_sentence()
    test_pipeline_offline_only_mocked()
    test_pipeline_gemma_error_keeps_draft_mocked()
    test_gemma_timeout_scales_with_length()
    test_ocr_looks_truncated_helper()
    print("ALL TESTS PASSED")
