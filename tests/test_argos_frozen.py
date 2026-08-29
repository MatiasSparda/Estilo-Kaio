"""Argos en exe: mismo binario como worker, paquetes en dir de usuario."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from unittest.mock import patch

import app.argos_translate as at
import app.argos_worker as aw


def test_worker_cmd_source():
    old_exe = sys.executable
    had_frozen = hasattr(sys, "frozen")
    old_frozen = getattr(sys, "frozen", None)
    sys.executable = r"C:\Python\python.exe"
    if had_frozen:
        sys.frozen = False
    try:
        cmd = at._worker_cmd()
    finally:
        sys.executable = old_exe
        if had_frozen:
            sys.frozen = old_frozen
        elif hasattr(sys, "frozen"):
            del sys.frozen
    assert cmd == [r"C:\Python\python.exe", "-m", "app.argos_worker"]


def test_worker_cmd_frozen():
    old_exe = sys.executable
    had_frozen = hasattr(sys, "frozen")
    old_frozen = getattr(sys, "frozen", None)
    sys.frozen = True
    sys.executable = r"C:\EstiloKaio.exe"
    try:
        cmd = at._worker_cmd()
    finally:
        sys.executable = old_exe
        if had_frozen:
            sys.frozen = old_frozen
        elif hasattr(sys, "frozen"):
            del sys.frozen
    assert cmd == [r"C:\EstiloKaio.exe", "--argos-worker"]


def test_prepare_argos_env_sets_package_dir_and_cpu():
    env = {"PATH": "x"}
    dest = Path("D:/tmp/argos-packages")
    with patch.object(aw, "_user_packages_dir", return_value=dest):
        out = at._prepare_argos_env(env)
    assert out["ARGOS_PACKAGES_DIR"] == str(dest)
    assert out["ARGOS_DEVICE_TYPE"] == "cpu"
    assert env.get("ARGOS_PACKAGES_DIR") is None


def test_copy_bundled_packages_when_en_es_missing(tmp_path):
    bundled = tmp_path / "meipass" / "argos-packages"
    src_pkg = bundled / "translate-en_es"
    src_pkg.mkdir(parents=True)
    (src_pkg / "metadata.json").write_text(
        '{"from_code":"en","to_code":"es"}', encoding="utf-8"
    )
    dest = tmp_path / "user-packages"
    dest.mkdir()
    aw._copy_bundled_packages(bundled, dest)
    assert (dest / "translate-en_es" / "metadata.json").is_file()


def test_copy_bundled_skips_when_pair_present(tmp_path):
    bundled = tmp_path / "bundle"
    src_pkg = bundled / "translate-en_es"
    src_pkg.mkdir(parents=True)
    (src_pkg / "metadata.json").write_text(
        '{"from_code":"en","to_code":"es"}', encoding="utf-8"
    )
    dest = tmp_path / "user"
    dest_pkg = dest / "translate-en_es"
    dest_pkg.mkdir(parents=True)
    (dest_pkg / "metadata.json").write_text(
        '{"from_code":"en","to_code":"es","mark":"user"}', encoding="utf-8"
    )
    aw._copy_bundled_packages(bundled, dest)
    assert '"mark":"user"' in dest_pkg.joinpath("metadata.json").read_text(
        encoding="utf-8"
    )


if __name__ == "__main__":
    import tempfile

    test_worker_cmd_source()
    test_worker_cmd_frozen()
    test_prepare_argos_env_sets_package_dir_and_cpu()
    with tempfile.TemporaryDirectory() as d:
        test_copy_bundled_packages_when_en_es_missing(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_copy_bundled_skips_when_pair_present(Path(d))
    print("ALL TESTS PASSED")
