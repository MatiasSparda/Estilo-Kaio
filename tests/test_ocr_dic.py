"""Tests del diccionario OCR."""

from app.ocr_dic import correct_ocr_text


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


if __name__ == "__main__":
    test_corrects_game_ocr_typos()
    print("ALL TESTS PASSED")
