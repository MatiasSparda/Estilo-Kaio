"""Tests del diccionario OCR."""

from app.ocr_dic import correct_ocr_text, detect_overlay_capture


def test_corrects_game_ocr_typos():
    src = (
        "Return the Relic to the Shrine of Icorus to resurrect the Lonly Unicorn.\n"
        "Seck Brother Gommo in Wildobor."
    )
    out = correct_ocr_text(src)
    assert "Seek" in out
    assert "Lonely" in out
    assert "Icarus" in out
    assert "Seck" not in out
    assert "Lonly" not in out


def test_detects_overlay_capture_mixed_languages():
    contaminated = (
        "Lo que te ha traído aquí, además de la fe en el señor de esas deidades.\n"
        "Lord of those lesser patron deities you would call the other eleven."
    )
    assert detect_overlay_capture(contaminated)
    clean = "What has brought you here, besides the True Faith in the Lord."
    assert not detect_overlay_capture(clean)


if __name__ == "__main__":
    test_corrects_game_ocr_typos()
    test_detects_overlay_capture_mixed_languages()
    print("ALL TESTS PASSED")
