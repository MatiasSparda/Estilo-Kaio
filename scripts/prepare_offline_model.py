"""Prepara modelo offline EN->ES (Marian OPUS-MT) para el worker.

Uso:
  pip install transformers sentencepiece huggingface_hub torch
  python scripts/prepare_offline_model.py

Salida: build/offline-en-es/ + engine.json
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "offline-en-es"
META = OUT / "engine.json"
HF_ID = "Helsinki-NLP/opus-mt-en-es"

_GATE_EN = (
    "Hmmm, you'd have to part with a good 7D 0S 0B for repairing the silver mace! "
    "he says, scratching the chin. The smith examines the damage closely. "
    "Which one of you will do the haggling?"
)


def _gate_ok(es: str) -> bool:
    """Aceptacion semantica (no igualdad con una frase fija)."""
    t = (es or "").casefold()
    if "7d" not in t:
        return False
    if "0s" not in t and "0b" not in t:
        return False
    if "maza" not in t:
        return False
    if "regate" not in t:
        return False
    # Basura tipica Argos
    if "parte con" in t and "pagar" not in t:
        return False
    return True


def _translate_marian(model_dir: Path, text: str) -> str:
    """Misma ruta que el worker (import diferido)."""
    import sys

    sys.path.insert(0, str(ROOT))
    from app.offline_worker import _translate

    return _translate(text, "en", "es")


def main() -> int:
    from huggingface_hub import snapshot_download

    if OUT.exists():
        shutil.rmtree(OUT)
    print(f"Descargando {HF_ID} -> {OUT}")
    snapshot_download(
        HF_ID,
        local_dir=str(OUT),
        local_dir_use_symlinks=False,
    )
    # Solo runtime Marian (PyTorch + SPM). Flax/TF inflan el zip ~600 MB.
    for junk in ("flax_model.msgpack", "tf_model.h5", ".gitattributes"):
        p = OUT / junk
        if p.is_file():
            p.unlink()
    out = _translate_marian(OUT, _GATE_EN)
    print("GATE OUT:", out)
    if not _gate_ok(out):
        print("GATE FAIL", file=sys.stderr)
        return 1
    META.write_text(
        json.dumps(
            {"engine": "marian", "hf_id": HF_ID, "pair": "en-es"},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("GATE OK -> marian")
    print(f"Listo: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
