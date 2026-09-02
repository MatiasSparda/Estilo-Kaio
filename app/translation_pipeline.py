"""Orquestación única: offline | offline_gemma | gemma."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from .ocr_dic import correct_blocks
from .translator import normalize_translation_provider


def translation_is_error(text: str) -> bool:
    t = (text or "").strip()
    return t.startswith("[Error:") or t.startswith("Error:")


def extract_error_detail(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("[Error:"):
        return t[8:-1].strip() if t.endswith("]") else t[7:].strip()
    if t.startswith("Error:"):
        return t[6:].strip()
    return t


def extract_translation_errors(results) -> list[str]:
    errs: list[str] = []
    if isinstance(results, str):
        if translation_is_error(results):
            msg = extract_error_detail(results)
            if msg:
                errs.append(msg)
        return errs
    for r in results or []:
        t = (r.get("translated") or "").strip()
        if translation_is_error(t):
            msg = extract_error_detail(t)
            if msg and msg not in errs:
                errs.append(msg)
    return errs


def gemma_timeout_for(text: str) -> float:
    n = len((text or "").strip())
    return max(90.0, 30.0 + n * 0.05)


def combined_source_text(blocks) -> str:
    parts: list[str] = []
    for b in blocks or []:
        if hasattr(b, "text"):
            t = b.text or ""
        elif isinstance(b, dict):
            t = b.get("text") or ""
        else:
            t = ""
        if t.strip():
            parts.append(t.strip())
    return "\n\n".join(parts)


@dataclass
class TranslationCallbacks:
    on_draft: Callable[[list], None] | None = None
    on_final: Callable[[list], None] | None = None
    on_gemma_error: Callable[[str], None] | None = None
    on_fatal: Callable[[str], None] | None = None


def _notify(cb: Callable | None, *args) -> None:
    if cb:
        cb(*args)


def _run_offline_only(corrected, src: str, tgt: str, callbacks: TranslationCallbacks) -> None:
    from .offline_translate import translate_blocks as offline_blocks

    try:
        results = offline_blocks(corrected, src, tgt, review=False)
        errs = extract_translation_errors(results)
        if errs:
            _notify(callbacks.on_fatal, errs[0])
            return
        _notify(callbacks.on_final, results)
    except Exception as e:
        _notify(callbacks.on_fatal, str(e))


def _run_gemma_only(corrected, src: str, tgt: str, callbacks: TranslationCallbacks) -> None:
    from .gemma_translate import translate_blocks as gemma_blocks

    timeout = gemma_timeout_for(combined_source_text(corrected))
    try:
        results = gemma_blocks(corrected, src, tgt, timeout=timeout, review=False)
        errs = extract_translation_errors(results)
        if errs:
            _notify(callbacks.on_fatal, errs[0])
            return
        _notify(callbacks.on_final, results)
    except Exception as e:
        _notify(callbacks.on_fatal, str(e))


def _run_offline_gemma_parallel(
    corrected, src: str, tgt: str, callbacks: TranslationCallbacks
) -> None:
    from .gemma_translate import is_server_running, translate_blocks as gemma_blocks
    from .offline_translate import translate_blocks as offline_blocks

    offline_out: list = []
    gemma_out: list = []
    gemma_note: list[str] = []
    timeout = gemma_timeout_for(combined_source_text(corrected))

    def run_offline():
        try:
            offline_out.append(offline_blocks(corrected, src, tgt, review=False))
        except Exception as e:
            offline_out.append(
                [
                    {
                        "label": "Error",
                        "source_text": "",
                        "translated": f"[Error: {e}]",
                    }
                ]
            )

    def run_gemma():
        if not is_server_running():
            gemma_note.append("off")
            return
        try:
            gemma_out.append(
                gemma_blocks(corrected, src, tgt, timeout=timeout, review=False)
            )
        except Exception as e:
            gemma_note.append(str(e))

    t_off = threading.Thread(target=run_offline, daemon=True)
    t_gem = threading.Thread(target=run_gemma, daemon=True)
    t_off.start()
    t_gem.start()
    t_off.join()

    draft = offline_out[0] if offline_out else []
    draft_errs = extract_translation_errors(draft)
    if draft_errs:
        _notify(callbacks.on_fatal, draft_errs[0])
        return
    _notify(callbacks.on_draft, draft)

    t_gem.join()
    if gemma_out:
        results = gemma_out[0]
        gemma_errs = extract_translation_errors(results)
        if gemma_errs:
            _notify(callbacks.on_gemma_error, gemma_errs[0])
            return
        _notify(callbacks.on_final, results)
        return

    note = gemma_note[0] if gemma_note else "error"
    if note == "off":
        _notify(
            callbacks.on_gemma_error,
            "Gemma apagado — solo borrador Offline",
        )
    else:
        _notify(callbacks.on_gemma_error, note)


def run_translation(
    blocks,
    *,
    provider: str,
    src: str,
    tgt: str,
    callbacks: TranslationCallbacks,
) -> None:
    """Ejecutar en thread worker (no bloquea UI)."""
    corrected = correct_blocks(list(blocks or []))
    p = normalize_translation_provider(provider or "offline")

    if p == "offline":
        _run_offline_only(corrected, src, tgt, callbacks)
    elif p == "offline_gemma":
        _run_offline_gemma_parallel(corrected, src, tgt, callbacks)
    elif p == "gemma":
        _run_gemma_only(corrected, src, tgt, callbacks)
    else:
        _notify(callbacks.on_fatal, f"Provider desconocido: {provider}")
