"""Tests de calidad offline (sin cargar Marian)."""

from app.offline_quality import (
    polish_spanish_mt,
    preprocess_english,
    protect_fragile,
    restore_fragile,
    score_candidate,
)


def test_protect_title_case_and_currency():
    src = "Oh, Tall Folk. Pay 7D 0S 0B please."
    prot, names = protect_fragile(src)
    assert "Tall Folk" in names
    assert "7D" not in names  # moneda sin placeholder
    assert "XNAME0X" in prot
    assert "7D" in prot
    back = restore_fragile("Oh, XNAME0X. Paga 7D 0S 0B.", names)
    assert "Tall Folk" in back
    assert "7D" in back


def test_part_with_calque_polish():
    en = "you'd have to part with a good 7D"
    es = "tendrías que separarte con un buen 7D"
    out = polish_spanish_mt(es, en)
    assert "pagar" in out.casefold()
    assert "separarte con" not in out.casefold()


def test_score_prefers_imperative():
    en = "Get back! The moon screams."
    good = "¡Atrás! La luna grita."
    bad = "La luna grita y se pone en marcha."
    assert score_candidate(en, good) > score_candidate(en, bad)


def test_preprocess_capitalizes_after_bang():
    out = preprocess_english("mace! he says.")
    assert "He says" in out


if __name__ == "__main__":
    test_protect_title_case_and_currency()
    test_part_with_calque_polish()
    test_score_prefers_imperative()
    test_preprocess_capitalizes_after_bang()
    print("ALL TESTS PASSED")
