"""Offline Marian: worker cmd frozen + moneda OCR."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import app.offline_translate as ot
from app.ocr_dic import correct_ocr_text


def test_worker_cmd_source():
    old_exe = sys.executable
    had_frozen = hasattr(sys, "frozen")
    old_frozen = getattr(sys, "frozen", None)
    sys.executable = r"C:\Python\python.exe"
    if had_frozen:
        sys.frozen = False
    try:
        cmd = ot._worker_cmd()
    finally:
        sys.executable = old_exe
        if had_frozen:
            sys.frozen = old_frozen
        elif hasattr(sys, "frozen"):
            del sys.frozen
    assert cmd == [r"C:\Python\python.exe", "-m", "app.offline_worker"]


def test_worker_cmd_frozen():
    old_exe = sys.executable
    had_frozen = hasattr(sys, "frozen")
    old_frozen = getattr(sys, "frozen", None)
    sys.frozen = True
    sys.executable = r"C:\EstiloKaio.exe"
    try:
        cmd = ot._worker_cmd()
    finally:
        sys.executable = old_exe
        if had_frozen:
            sys.frozen = old_frozen
        elif hasattr(sys, "frozen"):
            del sys.frozen
    assert cmd == [r"C:\EstiloKaio.exe", "--offline-worker"]


def test_currency_ocr_typography():
    # Tipografia OCR: S→5, D→O — no convierte a gp
    fixed = correct_ocr_text("pay a good 7O 05 0B for the mace")
    assert "7D" in fixed
    assert "0S" in fixed
    assert "0B" in fixed
    assert "gp" not in fixed.lower()


def test_currency_already_clean_untouched():
    src = "pay 7D 0S 0B please"
    assert "7D 0S 0B" in correct_ocr_text(src)


if __name__ == "__main__":
    test_worker_cmd_source()
    test_worker_cmd_frozen()
    test_currency_ocr_typography()
    test_currency_already_clean_untouched()
    print("ALL TESTS PASSED")
