"""Corrección OCR (diccionario wrong→right antes de traducir)."""

from __future__ import annotations

import re
from pathlib import Path

# Correcciones comunes de OCR en juegos (EN). Extensible vía guias/ocr_dic.txt
_BUILTIN: dict[str, str] = {
    "beyound": "beyond",
    "beoynd": "beyond",
    "accomodation": "accommodation",
    "acommodation": "accommodation",
    "honoured": "honored",
    "custorners": "customers",
    "customors": "customers",
    "interesfed": "interested",
    "dormltory": "dormitory",
    "dormltoty": "dormitory",
    "sultte": "suite",
    "sultes": "suites",
    "goas": "gods",
    "burries": "buries",
    "weli": "well",
    "weil": "well",
    "helio": "well",
    "gryphon": "gryphon",  # keep
    "teh": "the",
    "taht": "that",
    "wiht": "with",
    "fro m": "from",
    "perperson": "per person",
}


def _load_user_dic() -> dict[str, str]:
    """Formato diccionario: original=corregido (una por línea)."""
    roots = [
        Path(__file__).resolve().parents[1] / "guias" / "ocr_dic.txt",
        Path(__file__).resolve().parents[1] / "ocr_dic.txt",
    ]
    out: dict[str, str] = {}
    for path in roots:
        if not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                wrong, right = line.split("=", 1)
                wrong, right = wrong.strip(), right.strip()
                if wrong and right:
                    out[wrong.lower()] = right
        except OSError:
            continue
    return out


def _merged_dic() -> dict[str, str]:
    d = dict(_BUILTIN)
    d.update(_load_user_dic())
    return d


_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ']+")


def correct_ocr_text(text: str, *, passes: int = 2) -> str:
    """Aplica diccionario OCR (corrección ortográfica previa a traducir)."""
    if not (text or "").strip():
        return text or ""
    dic = _merged_dic()
    if not dic:
        return text

    def repl(m: re.Match) -> str:
        word = m.group(0)
        key = word.lower()
        if key not in dic:
            return word
        fixed = dic[key]
        # Preservar capitalización gruesa
        if word.isupper():
            return fixed.upper()
        if word[0].isupper():
            return fixed[:1].upper() + fixed[1:]
        return fixed

    out = text
    for _ in range(max(1, passes)):
        out = _WORD_RE.sub(repl, out)
    return out


def correct_blocks(blocks: list) -> list:
    """Corrige .text de TextBlock o dict in-place / copia ligera."""
    from .ocr_types import TextBlock

    out = []
    for b in blocks or []:
        if isinstance(b, TextBlock):
            out.append(
                TextBlock(
                    text=correct_ocr_text(b.text),
                    x=b.x,
                    y=b.y,
                    w=b.w,
                    h=b.h,
                    label=b.label,
                    img_w=getattr(b, "img_w", 0) or 0,
                    img_h=getattr(b, "img_h", 0) or 0,
                )
            )
        elif isinstance(b, dict):
            nb = dict(b)
            nb["text"] = correct_ocr_text(nb.get("text") or "")
            out.append(nb)
        else:
            out.append(b)
    return out
