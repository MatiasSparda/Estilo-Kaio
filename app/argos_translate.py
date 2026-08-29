"""Traducción offline con Argos Translate (proceso aislado, sin bloqueos)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from . import argos_worker as _argos_worker

_CHUNK_LIMIT = 4500
_WORKER_TIMEOUT_S = 120.0
_WORKER_TIMEOUT_FROZEN_S = 180.0


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _worker_cmd() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--argos-worker"]
    return [sys.executable, "-m", "app.argos_worker"]


def _prepare_argos_env(env: dict) -> dict:
    out = dict(env)
    dest = _argos_worker._user_packages_dir()
    out["ARGOS_PACKAGES_DIR"] = str(dest)
    out.update(_argos_worker.ARGOS_QUALITY_ENV)
    out["PYTHONIOENCODING"] = "utf-8"
    return out


def _translate_once(text: str, source: str, target: str) -> str:
    """Traduce en subproceso limpio (evita WinError 1114 con torch/c10.dll)."""
    payload = json.dumps(
        {"text": text, "source": source, "target": target},
        ensure_ascii=False,
    )
    env = _prepare_argos_env(os.environ.copy())
    frozen = getattr(sys, "frozen", False)
    if frozen:
        cwd = os.path.dirname(sys.executable)
        timeout = _WORKER_TIMEOUT_FROZEN_S
    else:
        root = _project_root()
        env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
        cwd = root
        timeout = _WORKER_TIMEOUT_S

    run_kw: dict = {
        "input": payload,
        "capture_output": True,
        "encoding": "utf-8",
        "timeout": timeout,
        "env": env,
        "cwd": cwd,
    }
    if sys.platform == "win32":
        run_kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.run(_worker_cmd(), **run_kw)
    raw = (proc.stdout or "").strip()
    if not raw:
        err = (proc.stderr or "").strip()
        if frozen:
            raise RuntimeError(err or "Argos no arrancó en el ejecutable.")
        raise RuntimeError(
            err or "Argos no respondió. Verificá: pip install argostranslate"
        )
    data = json.loads(raw)
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "Argos falló sin detalle.")
    return data.get("translated") or ""


def translate_text(text: str, source: str = "en", target: str = "es") -> str:
    """Traduce texto offline con Argos."""
    chunk = (text or "").strip()
    if not chunk:
        return ""
    src = (source or "en").strip()
    tgt = (target or "es").strip()
    if src == tgt:
        return chunk

    if len(chunk) <= _CHUNK_LIMIT:
        return _translate_once(chunk, src, tgt)

    parts: list[str] = []
    buf: list[str] = []
    size = 0
    for para in chunk.split("\n"):
        add = len(para) + (1 if buf else 0)
        if buf and size + add > _CHUNK_LIMIT:
            parts.append(_translate_once("\n".join(buf), src, tgt))
            buf = [para]
            size = len(para)
        else:
            buf.append(para)
            size += add
    if buf:
        parts.append(_translate_once("\n".join(buf), src, tgt))
    return "\n".join(parts)


def translate_blocks(
    blocks: list,
    source: str = "en",
    target: str = "es",
    *,
    review: bool = False,
    review_timeout: float = 35.0,
) -> list[dict]:
    """Misma forma de salida que gemma_translate.translate_blocks."""
    normalized: list[tuple[str, str, object]] = []
    for block in blocks or []:
        if hasattr(block, "text"):
            src_text = block.text or ""
            label = getattr(block, "label", "Texto") or "Texto"
        else:
            src_text = (block or {}).get("text") or ""
            label = (block or {}).get("label") or "Texto"
        if src_text.strip():
            normalized.append((src_text, label, block))

    if not normalized:
        return []

    from .ocr_engine import _looks_like_party_roster

    narrative: list[tuple[str, str, object]] = []
    extra: list[tuple[str, str, object]] = []
    for item in normalized:
        src, label, block = item
        if label.startswith("Party") and _looks_like_party_roster(src):
            extra.append(item)
        else:
            narrative.append(item)
    if len(narrative) > 1:
        combined_src = "\n\n".join(s for s, _, _ in narrative)
        first = narrative[0]
        normalized = [(combined_src, "Diálogo", first[2])] + extra

    def _geom(block, key: str, default=0.0) -> float:
        if hasattr(block, key):
            return float(getattr(block, key, default) or default)
        return float((block or {}).get(key) or default)

    out: list[dict] = []
    for src_text, label, block in normalized:
        try:
            translated = translate_text(src_text, source, target)
        except Exception as e:
            translated = f"[Error: {e}]"
        out.append(
            {
                "label": label,
                "source_text": src_text,
                "translated": translated,
                "x": _geom(block, "x"),
                "y": _geom(block, "y"),
                "w": _geom(block, "w"),
                "h": _geom(block, "h"),
                "img_w": _geom(block, "img_w"),
                "img_h": _geom(block, "img_h"),
            }
        )
    if review:
        from .review_translate import review_block_results

        return review_block_results(out, source, target, timeout=review_timeout)
    return out


def translate_text_with_review(
    text: str,
    source: str = "en",
    target: str = "es",
    *,
    timeout: float = 35.0,
) -> str:
    from .review_translate import translate_text_with_review as review_fn

    return review_fn(translate_text, text, source, target, timeout=timeout)
