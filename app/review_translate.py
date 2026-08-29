"""Revisión Gemma sobre borradores (Argos u otros motores rápidos)."""

from __future__ import annotations


def review_block_results(
    results: list[dict],
    source: str,
    target: str,
    *,
    timeout: float = 35.0,
) -> list[dict]:
    from .gemma_translate import review_translation

    out: list[dict] = []
    for r in results or []:
        row = dict(r)
        draft = (row.get("translated") or "").strip()
        src_text = row.get("source_text") or ""
        if not draft or draft.startswith("[Error:"):
            out.append(row)
            continue
        reviewed = review_translation(
            src_text,
            draft,
            source,
            target,
            timeout=timeout,
            max_tokens=min(512, 128 + len(src_text) * 2),
        )
        row["translated"] = reviewed or draft
        out.append(row)
    return out


def translate_text_with_review(
    draft_fn,
    text: str,
    source: str = "en",
    target: str = "es",
    *,
    timeout: float = 35.0,
) -> str:
    from .gemma_translate import review_translation

    draft = draft_fn(text, source, target)
    if not draft or draft.startswith("[Error:"):
        return draft
    return review_translation(
        text, draft, source, target, timeout=timeout
    ) or draft
