"""Traducción online con MyMemory (sin Google, sin API key)."""

from __future__ import annotations

from deep_translator import MyMemoryTranslator
from deep_translator.exceptions import LanguageNotSupportedException

# MyMemory usa nombres completos en minúsculas.
_LANG = {
    "en": "english",
    "es": "spanish",
    "ja": "japanese",
    "ko": "korean",
    "zh-CN": "chinese simplified",
    "zh-TW": "chinese traditional",
    "pt": "portuguese",
    "fr": "french",
    "de": "german",
    "it": "italian",
    "ru": "russian",
    "ar": "arabic",
}

_CHUNK_LIMIT = 4500


def _mymemory_codes(source: str, target: str) -> tuple[str, str]:
    src = _LANG.get(source, source.lower())
    tgt = _LANG.get(target, target.lower())
    return src, tgt


def _looks_like_api_error(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    if "no translation was found" in t:
        return True
    if t.startswith("<html") or "<!doctype html" in t[:32]:
        return True
    return False


def _translate_once(text: str, source: str, target: str) -> str:
    src, tgt = _mymemory_codes(source, target)
    if src == tgt:
        return text
    return MyMemoryTranslator(source=src, target=tgt).translate(text) or ""


def translate_text(text: str, source: str = "en", target: str = "es") -> str:
    """Traduce texto online vía MyMemory."""
    if not (text or "").strip():
        return ""
    chunk = text.strip()
    if len(chunk) <= _CHUNK_LIMIT:
        out = _translate_once(chunk, source, target)
        if _looks_like_api_error(out):
            raise RuntimeError(
                "MyMemory no devolvió traducción. Probá Argos (offline) o Gemma."
            )
        return out

    parts: list[str] = []
    buf: list[str] = []
    size = 0
    for para in chunk.split("\n"):
        add = len(para) + (1 if buf else 0)
        if buf and size + add > _CHUNK_LIMIT:
            piece = _translate_once("\n".join(buf), source, target)
            if _looks_like_api_error(piece):
                raise RuntimeError("MyMemory falló en un fragmento largo.")
            parts.append(piece)
            buf = [para]
            size = len(para)
        else:
            buf.append(para)
            size += add
    if buf:
        piece = _translate_once("\n".join(buf), source, target)
        if _looks_like_api_error(piece):
            raise RuntimeError("MyMemory falló en un fragmento largo.")
        parts.append(piece)
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
        except LanguageNotSupportedException as e:
            translated = f"[Error: idioma no soportado: {e}]"
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
        return review_block_results(out, source, target, timeout=review_timeout)
    return out


def review_block_results(
    results: list[dict],
    source: str,
    target: str,
    *,
    timeout: float = 35.0,
) -> list[dict]:
    """Aplica revisión Gemma sobre borradores online."""
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
    text: str,
    source: str = "en",
    target: str = "es",
    *,
    timeout: float = 35.0,
) -> str:
    """Borrador MyMemory + revisión Gemma."""
    from .gemma_translate import review_translation

    draft = translate_text(text, source, target)
    if not draft or draft.startswith("[Error:"):
        return draft
    return review_translation(
        text, draft, source, target, timeout=timeout
    ) or draft
