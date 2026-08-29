"""Worker aislado para Argos (evita conflicto torch/c10.dll con Gemma/GPU)."""

from __future__ import annotations

import json
import sys


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
