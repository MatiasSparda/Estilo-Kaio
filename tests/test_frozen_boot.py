"""PyInstaller corre app/__main__.py como script: sin imports relativos."""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_MAIN = _ROOT / "app" / "__main__.py"


def test_entrypoint_has_no_relative_imports():
    tree = ast.parse(_MAIN.read_text(encoding="utf-8"))
    bad = [
        (n.module, n.level)
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.level
    ]
    assert bad == [], f"imports relativos en app/__main__.py: {bad}"


def test_entrypoint_gates_argos_worker_before_gui():
    src = _MAIN.read_text(encoding="utf-8")
    worker_at = src.find("--argos-worker")
    gui_at = src.find("from app.main import")
    assert worker_at != -1
    assert gui_at != -1
    assert worker_at < gui_at


if __name__ == "__main__":
    test_entrypoint_has_no_relative_imports()
    test_entrypoint_gates_argos_worker_before_gui()
    print("ALL TESTS PASSED")
