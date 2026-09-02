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
    "seck": "Seek",
    "lonly": "Lonely",
    "icorus": "Icarus",
}


def detect_overlay_capture(text: str) -> bool:
    """True si el OCR mezcla español e inglés (típico: captura encima del overlay)."""
    if not (text or "").strip():
        return False
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if len(lines) < 2:
        return False

    spanish_fn = re.compile(
        r"\b(?:que|de|la|el|los|las|en|un|una|por|con|es|son|ha|te|se|del|al|"
        r"qué|está|están|además|también|pero|como|más|aquí|sin|sobre|entre|"
        r"desde|hasta|muy|bien|solo|sólo)\b",
        re.I,
    )
    english_fn = re.compile(
        r"\b(?:the|of|you|your|would|what|has|have|been|here|those|this|that|"
        r"with|from|and|are|was|were|for|not|but|they|their|there|will|should|"
        r"could|can|may|might|must|also|just|only|even|when|where|which|who|"
        r"how|why|all|any|some|than|too|very|into|about|after|before|call)\b",
        re.I,
    )
    diacritics = re.compile(r"[áéíóúñÁÉÍÓÚÑ]")

    def _looks_spanish(ln: str) -> bool:
        return bool(diacritics.search(ln)) or len(spanish_fn.findall(ln)) >= 3

    def _looks_english(ln: str) -> bool:
        return len(english_fn.findall(ln)) >= 3 and not diacritics.search(ln)

    has_es = any(_looks_spanish(ln) for ln in lines)
    has_en = any(_looks_english(ln) for ln in lines)
    return has_es and has_en


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
# Moneda del juego: 7D 0S 0B — OCR suele leer S como 5 y D como O.
_CURRENCY_TRIPLE = re.compile(
    r"\b(\d+)([DO])\s+(\d+)([S5])\s+(\d+)([B8])\b",
    re.I,
)


def _fix_currency_typography(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        a, u1, b, u2, c, u3 = m.groups()
        d = "D"
        s = "S"
        bb = "B"
        return f"{a}{d} {b}{s} {c}{bb}"

    return _CURRENCY_TRIPLE.sub(repl, text or "")


def correct_ocr_text(text: str, *, passes: int = 2) -> str:
    """Aplica diccionario OCR (corrección ortográfica previa a traducir)."""
    if not (text or "").strip():
        return text or ""
    out = _fix_currency_typography(text)
    dic = _merged_dic()
    if not dic:
        return out

    def repl(m: re.Match) -> str:
        word = m.group(0)
        key = word.lower()
        if key not in dic:
            return word
        fixed = dic[key]
        if word.isupper():
            return fixed.upper()
        if word[0].isupper():
            return fixed[:1].upper() + fixed[1:]
        return fixed

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
