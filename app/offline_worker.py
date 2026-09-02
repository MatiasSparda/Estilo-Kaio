"""Worker aislado: Marian OPUS-MT EN->ES (local, sin limites de API)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .offline_quality import (
    polish_spanish_mt,
    preprocess_english,
    protect_fragile,
    restore_fragile,
    score_candidate,
    split_sentences,
)

_model = None
_tokenizer = None


def _model_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "offline-en-es"
        if bundled.is_dir():
            return bundled
    root = Path(__file__).resolve().parents[1]
    return root / "build" / "offline-en-es"


def _user_cache_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "EstiloKaio" / "offline-en-es"


def _resolve_model_dir() -> Path:
    bundled = _model_dir()
    if not getattr(sys, "frozen", False):
        return bundled
    dest = _user_cache_dir()
    meta = dest / "engine.json"
    if meta.is_file():
        return dest
    if bundled.is_dir() and any(bundled.iterdir()):
        import shutil

        dest.mkdir(parents=True, exist_ok=True)
        shutil.copytree(bundled, dest, dirs_exist_ok=True)
        return dest
    return bundled


def _ensure_model():
    global _model, _tokenizer
    if _model is not None and _tokenizer is not None:
        return
    from transformers import MarianMTModel, MarianTokenizer

    path = _resolve_model_dir()
    if not path.is_dir():
        raise RuntimeError(
            f"Falta modelo offline en {path}. Corré: python scripts/prepare_offline_model.py"
        )
    _tokenizer = MarianTokenizer.from_pretrained(str(path))
    _model = MarianMTModel.from_pretrained(str(path))
    # Evitar warning max_length vs max_new_tokens
    try:
        _model.generation_config.max_length = None
    except Exception:
        pass


def _generate_one(sentence: str) -> str:
    _ensure_model()
    assert _tokenizer is not None and _model is not None
    batch = _tokenizer(
        [sentence],
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=512,
    )
    gen = _model.generate(
        **batch,
        num_beams=6,
        max_new_tokens=256,
        length_penalty=1.1,
        early_stopping=True,
    )
    return _tokenizer.decode(gen[0], skip_special_tokens=True)


def _translate_by_sentences(text: str) -> str:
    parts: list[str] = []
    for sent in split_sentences(text):
        if not sent.strip():
            parts.append("")
            continue
        parts.append(_generate_one(sent))
    # Reconstruir: oraciones unidas con espacio; vacíos = salto de párrafo
    out: list[str] = []
    buf: list[str] = []
    for p in parts:
        if p == "":
            if buf:
                out.append(" ".join(buf))
                buf = []
            out.append("")
        else:
            buf.append(p)
    if buf:
        out.append(" ".join(buf))
    return "\n".join(out).strip()


def _translate_full(text: str) -> str:
    # Marian aguanta ~512 tokens; trocear párrafos largos.
    paras = (text or "").split("\n")
    out: list[str] = []
    for para in paras:
        if not para.strip():
            out.append("")
            continue
        if len(para) > 420:
            out.append(_translate_by_sentences(para))
        else:
            out.append(_generate_one(para.strip()))
    return "\n".join(out).strip()


def _translate_sentences(text: str) -> str:
    cleaned = preprocess_english(text)
    if not cleaned:
        return ""
    protected, names = protect_fragile(cleaned)

    by_sent = _translate_by_sentences(protected)
    full = _translate_full(protected)
    by_sent = restore_fragile(by_sent, names)
    full = restore_fragile(full, names)

    # Elegir el candidato más fiel al inglés (sin hardcodear glosas).
    cands = [by_sent, full]
    best = max(cands, key=lambda es: score_candidate(cleaned, es))
    return polish_spanish_mt(best, cleaned)


def _translate(text: str, source: str, target: str) -> str:
    chunk = (text or "").strip()
    if not chunk:
        return ""
    src = (source or "en").strip()
    tgt = (target or "es").strip()
    if src == tgt:
        return chunk
    if src != "en" or tgt != "es":
        raise RuntimeError(
            f"Offline Marian solo soporta en->es (pedido {src}->{tgt})."
        )
    return _translate_sentences(chunk)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        text = payload.get("text") or ""
        source = payload.get("source") or "en"
        target = payload.get("target") or "es"
        result = _translate(text, source, target)
        json.dump({"ok": True, "translated": result}, sys.stdout, ensure_ascii=True)
        return 0
    except Exception as e:
        json.dump({"ok": False, "error": str(e)}, sys.stdout, ensure_ascii=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
