"""Traducción online vía Google Translate (API web, sin IA local)."""

from __future__ import annotations

from deep_translator import GoogleTranslator
from deep_translator.exceptions import (
    LanguageNotSupportedException,
    NotValidPayload,
    TranslationNotFound,
)

# deep-translator usa códigos ISO; zh-CN / zh-TW están soportados.
_GOOGLE_LANG = {
    "en": "en",
    "es": "es",
    "ja": "ja",
    "ko": "ko",
    "zh-CN": "zh-CN",
    "zh-TW": "zh-TW",
    "pt": "pt",
    "fr": "fr",
    "de": "de",
    "it": "it",
    "ru": "ru",
    "ar": "ar",
}


def _map_lang(code: str) -> str:
    return _GOOGLE_LANG.get(code, code)


def translate_text(text: str, source: str = "en", target: str = "es") -> str:
    """Traduce un texto con Google Translate. Requiere internet."""
    if not (text or "").strip():
        return ""
    src = _map_lang(source)
    tgt = _map_lang(target)
    if src == tgt:
        return text.strip()
    try:
        # Google limita ~5000 caracteres por request
        chunk = text.strip()
        if len(chunk) <= 4500:
            return GoogleTranslator(source=src, target=tgt).translate(chunk) or ""
        parts: list[str] = []
        buf: list[str] = []
        size = 0
        for para in chunk.split("\n"):
            # +1 por el salto de línea al unir
            add = len(para) + (1 if buf else 0)
            if buf and size + add > 4500:
                parts.append(
                    GoogleTranslator(source=src, target=tgt).translate("\n".join(buf))
                    or ""
                )
                buf = [para]
                size = len(para)
            else:
                buf.append(para)
                size += add
        if buf:
            parts.append(
                GoogleTranslator(source=src, target=tgt).translate("\n".join(buf))
                or ""
            )
        return "\n".join(parts)
    except LanguageNotSupportedException as e:
        raise RuntimeError(f"Idioma no soportado por Google Translate: {e}") from e
    except (NotValidPayload, TranslationNotFound) as e:
        raise RuntimeError(f"Google Translate no pudo traducir: {e}") from e
    except Exception as e:
        raise RuntimeError(
            f"Error de Google Translate (¿hay internet?): {e}"
        ) from e


def translate_blocks(
    blocks: list,
    source: str = "en",
    target: str = "es",
    *,
    review: bool = False,
    review_timeout: float = 35.0,
) -> list[dict]:
    """Misma forma de salida que gemma_translate.translate_blocks.

    Si review=True, tras Google aplica la pasada QA de Gemma (requiere LiteRT).
    """
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
        return review_block_results(
            out, source, target, timeout=review_timeout
        )
    return out


def review_block_results(
    results: list[dict],
    source: str,
    target: str,
    *,
    timeout: float = 35.0,
) -> list[dict]:
    """Aplica revisión Gemma sobre borradores (p. ej. de Google)."""
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
    """Google borrador + revisión Gemma."""
    from .gemma_translate import review_translation

    draft = translate_text(text, source, target)
    if not draft or draft.startswith("[Error:"):
        return draft
    return review_translation(
        text, draft, source, target, timeout=timeout
    ) or draft
