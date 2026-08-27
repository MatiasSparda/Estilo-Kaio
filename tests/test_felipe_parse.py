"""Parse FELIPE / strip de pasos de guía."""

from app.guide_parser import (
    extract_felipe_line,
    extract_fuente_line,
    strip_fuente_from_steps,
)


def test_extract_felipe_and_fuente():
    raw = (
        "Andá al norte y hablá con el hermit.\n"
        "FUENTE: Go north and talk to the hermit\n"
        "FELIPE: Bacán weón, dale pa'l norte no más\n"
    )
    assert extract_fuente_line(raw) == "Go north and talk to the hermit"
    assert "Bacán" in (extract_felipe_line(raw) or "")
    steps = strip_fuente_from_steps(raw)
    assert "FUENTE" not in steps.upper()
    assert "FELIPE" not in steps.upper()
    assert "norte" in steps.lower()


def test_strip_without_felipe():
    raw = "Tip útil.\nFUENTE: Tip útil."
    assert extract_felipe_line(raw) is None
    assert "Tip útil" in strip_fuente_from_steps(raw)


def test_not_found_style_no_felipe_required():
    raw = "No encontré información sobre esto en la guía."
    assert extract_felipe_line(raw) is None
    assert extract_fuente_line(raw) is None
