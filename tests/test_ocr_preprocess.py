"""Preprocess OCR: RapidOCR necesita variante nativa (upscale solo rompe deteccion)."""

from pathlib import Path

from PIL import Image

from app.ocr_engine import preprocess_variants_for, OCREngine

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ocr" / "tall_folk_dialog.png"


def test_rapidocr_variants_include_native_size():
    img = Image.new("RGB", (320, 200), (80, 50, 30))
    variants = preprocess_variants_for("rapidocr", img)
    assert variants, "sin variantes"
    assert variants[0].size == img.size


def test_rapidocr_reads_tall_folk_fixture():
    if not _FIXTURE.is_file():
        raise AssertionError(f"Falta fixture {_FIXTURE}")
    img = Image.open(_FIXTURE).convert("RGB")
    eng = OCREngine("en", "rapidocr")
    if not eng._rapidocr.is_available() or not eng._rapidocr._ensure_engine():
        print("SKIP rapidocr no disponible:", eng._rapidocr.last_error)
        return
    blocks = eng.extract_blocks(img)
    joined = " ".join(b.text for b in blocks).lower()
    assert blocks, "RapidOCR no detecto texto en dialogo pixel"
    assert "tall" in joined or "folk" in joined or "faith" in joined
    # Con fallback multi-motor debe leer el cierre del dialogo (OneOCR si Rapid corta).
    assert "eleven" in joined or "other" in joined, (
        f"OCR truncado al final del dialogo: {joined!r}"
    )


def test_extract_sets_truncated_flag_when_appropriate():
    from app.ocr_engine import ocr_looks_truncated

    dialog = "Line one.\nLine two without ending punct"
    assert ocr_looks_truncated(dialog)
    assert not ocr_looks_truncated("Line one.\nLine two.")
    if not _FIXTURE.is_file():
        return
    img = Image.open(_FIXTURE).convert("RGB")
    eng = OCREngine("en", "rapidocr")
    blocks = eng.extract_blocks(img)
    if not blocks:
        return
    assert hasattr(eng, "last_ocr_truncated")
    assert isinstance(eng.last_ocr_truncated, bool)
    if not eng.last_ocr_truncated:
        joined = eng.last_ocr_joined or " ".join(b.text for b in blocks)
        assert joined.strip()


if __name__ == "__main__":
    test_rapidocr_variants_include_native_size()
    test_rapidocr_reads_tall_folk_fixture()
    test_extract_sets_truncated_flag_when_appropriate()
    print("ALL TESTS PASSED")
