"""Worker aislado para Argos (evita conflicto torch/c10.dll con Gemma/GPU)."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def _user_packages_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "EstiloKaio" / "argos-packages"


def _bundled_packages_dir() -> Path | None:
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None
    path = Path(meipass) / "argos-packages"
    return path if path.is_dir() else None


def _has_language_pair(packages_dir: Path, source: str, target: str) -> bool:
    if not packages_dir.is_dir():
        return False
    for meta in packages_dir.glob("*/metadata.json"):
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("from_code") == source and data.get("to_code") == target:
            return True
    return False


def _copy_bundled_packages(bundled: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if _has_language_pair(dest, "en", "es"):
        return
    if not bundled.is_dir():
        return
    shutil.copytree(bundled, dest, dirs_exist_ok=True)


def _bootstrap_argos_runtime() -> None:
    dest = _user_packages_dir()
    dest.mkdir(parents=True, exist_ok=True)
    bundled = _bundled_packages_dir()
    if bundled is not None:
        _copy_bundled_packages(bundled, dest)
    os.environ["ARGOS_PACKAGES_DIR"] = str(dest)
    os.environ["ARGOS_DEVICE_TYPE"] = "cpu"
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


def _ensure_language_pair(source: str, target: str) -> None:
    import argostranslate.package as pkg
    import argostranslate.translate as tr

    src = (source or "en").strip()
    tgt = (target or "es").strip()
    if src == tgt:
        return

    installed = tr.get_installed_languages()
    for lang in installed:
        if lang.code != src:
            continue
        for translation in lang.translations_from:
            if translation.to_lang.code == tgt:
                return

    try:
        pkg.update_package_index()
        available = pkg.get_available_packages()
        pair = next(
            (p for p in available if p.from_code == src and p.to_code == tgt),
            None,
        )
        if pair is None:
            raise RuntimeError(f"Argos no tiene paquete {src}→{tgt}.")
        path = pair.download()
        pkg.install_from_path(path)
    except Exception as e:
        if getattr(sys, "frozen", False):
            raise RuntimeError(
                f"Argos no tiene el par {src}-{tgt} offline y no pudo descargarlo. {e}"
            ) from e
        raise


def _translate(text: str, source: str, target: str) -> str:
    from argostranslate import translate

    chunk = (text or "").strip()
    if not chunk:
        return ""
    src = (source or "en").strip()
    tgt = (target or "es").strip()
    if src == tgt:
        return chunk
    _ensure_language_pair(src, tgt)
    return translate.translate(chunk, src, tgt) or ""


def main() -> int:
    _bootstrap_argos_runtime()
    try:
        payload = json.load(sys.stdin)
        text = payload.get("text") or ""
        source = payload.get("source") or "en"
        target = payload.get("target") or "es"
        result = _translate(text, source, target)
        json.dump({"ok": True, "translated": result}, sys.stdout, ensure_ascii=False)
        return 0
    except Exception as e:
        json.dump({"ok": False, "error": str(e)}, sys.stdout, ensure_ascii=False)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
