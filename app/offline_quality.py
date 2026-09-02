"""Mejoras genéricas EN→ES offline (sin glosarios de diálogo)."""

from __future__ import annotations

import re

# Title Case multi-palabra (nombres de fantasía / facciones).
_TITLE_CASE = re.compile(
    r"\b("
    r"[A-Z][a-z]+"
    r"(?:\s+(?:of|the|and|de|del|la|los|las)\s+[A-Z][a-z]+|\s+[A-Z][a-z]+)+"
    r")\b"
)

# Moneda del juego u otros tokens alfanuméricos frágiles.
_KEEP_TOKEN = re.compile(r"\b\d+[A-Za-z]\b")

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def preprocess_english(text: str) -> str:
    """Normaliza OCR/diálogo antes de Marian."""
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("„", '"').replace("“", '"').replace("”", '"').replace("‟", '"')
    t = t.replace("‚", "'").replace("‘", "'").replace("’", "'")
    # Líneas de diálogo OCR → un párrafo (Marian pierde imperativos si se corta mal).
    lines = [ln.strip() for ln in t.split("\n")]
    paras: list[str] = []
    buf: list[str] = []
    for ln in lines:
        if not ln:
            if buf:
                paras.append(" ".join(buf))
                buf = []
            paras.append("")
        else:
            buf.append(ln)
    if buf:
        paras.append(" ".join(buf))
    t = "\n".join(paras)
    # "mace! he says" → "mace! He says" (mejor frontera de oración)
    t = re.sub(
        r"([.!?])\s+([a-záéíóúñ])",
        lambda m: f"{m.group(1)} {m.group(2).upper()}",
        t,
    )
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def protect_fragile(text: str) -> tuple[str, list[str]]:
    """Placeholder estable para Title Case. Moneda (7D) Marian ya la conserva."""
    names: list[str] = []

    def _keep(m: re.Match[str]) -> str:
        names.append(m.group(0))
        return f"XNAME{len(names) - 1}X"

    out = _TITLE_CASE.sub(_keep, text or "")
    return out, names


def restore_fragile(text: str, names: list[str]) -> str:
    out = text or ""
    for i, name in enumerate(names):
        for tok in (
            f"XNAME{i}X",
            f"xname{i}x",
            f"Xname{i}X",
            f"XNAME {i} X",
            f"XNAME{i} X",
            f"# {i} #",
            f"#{i}#",
        ):
            out = out.replace(tok, name)
    return out


def split_sentences(text: str) -> list[str]:
    out: list[str] = []
    for para in (text or "").replace("\r\n", "\n").split("\n"):
        stripped = para.strip()
        if not stripped:
            out.append("")
            continue
        bits = [b.strip() for b in _SENT_SPLIT.split(stripped) if b.strip()]
        out.extend(bits or [stripped])
    return out


def score_candidate(english: str, spanish: str) -> int:
    """Heurística barata: conservar moneda/nombres, no comerse imperativos."""
    en = english or ""
    es = spanish or ""
    if not es.strip():
        return -1000
    score = 0
    for m in _KEEP_TOKEN.findall(en):
        if m in es or m.upper() in es.upper():
            score += 25
        else:
            score -= 40
    # Nombres Title Case del EN que siguen en ES (protegidos o literales)
    for m in _TITLE_CASE.findall(en):
        if m in es:
            score += 15
        elif m.casefold() in es.casefold():
            score += 8
        else:
            # Castigado suave: a veces se traduce (True Faith → Verdadera Fe)
            score -= 2
    ratio = len(es) / max(len(en), 1)
    if 0.65 <= ratio <= 1.75:
        score += 8
    else:
        score -= 12
    if "?" in en and ("¿" in es or "?" in es):
        score += 6
    # Imperativo corto al inicio no debe desaparecer
    if re.match(r"^(Get|Go|Stop|Wait|Look|Come|Run|Hold|Stay)\b", en, re.I):
        first = es.strip().split(None, 1)[0].casefold() if es.strip() else ""
        if first in {"la", "el", "los", "las", "un", "una"}:
            score -= 20
        if "atrás" in es.casefold() or "espera" in es.casefold() or "mira" in es.casefold():
            score += 10
    # Inglés crudo restante (malo), ignorando tokens ¤
    leftovers = re.findall(r"\b[A-Za-z]{4,}\b", es)
    junk = 0
    for w in leftovers:
        if w.startswith("¤"):
            continue
        if w.istitle() and w in en:
            continue
        if w.casefold() in {
            "hmmm",
            "ok",
            "okay",
            "boss",
            "item",
            "quest",
        }:
            continue
        # palabras ES comunes
        if w.casefold() in {
            "para",
            "como",
            "esta",
            "este",
            "esto",
            "aqui",
            "aquí",
            "señor",
            "senor",
            "verdadera",
            "otras",
            "once",
            "dice",
            "quien",
            "quién",
            "ustedes",
            "tendrias",
            "tendrías",
            "tendria",
            "tendría",
            "reparar",
            "maza",
            "plata",
            "plateada",
            "herrero",
            "examina",
            "dano",
            "daño",
            "cerca",
            "regatear",
            "regateo",
            "barbilla",
            "rasca",
            "rascándose",
            "ademas",
            "además",
            "deidades",
            "menores",
            "llamarías",
            "llamarías",
            "gente",
            "alta",
            "traído",
            "traido",
            "fe",
            "patronas",
            "mecenas",
            "luna",
            "grita",
            "gira",
            "lugar",
            "atrás",
            "atras",
        }:
            continue
        if re.fullmatch(r"[A-Za-z]+", w) and w.casefold() not in en.casefold():
            # posible inglés no traducido
            if w[0].isupper() and " " + w in (" " + en):
                junk += 1
            elif w.islower() and w in en.casefold():
                junk += 2
    score -= junk * 3
    return score


def polish_spanish_mt(spanish: str, english: str) -> str:
    """Post-edits lingüísticos guiados por el inglés (no frases de juego)."""
    out = spanish or ""
    en = english or ""
    en_l = en.casefold()

    # part with (money/goods) → pagar / desprenderse — calco típico Marian
    if re.search(r"\bpart with\b", en_l):
        out = re.sub(
            r"\b(tendr[ií]as? que |tendr[ií]a que |deber[ií]as? |hay que )?"
            r"separarte con\b",
            r"\1pagar",
            out,
            flags=re.I,
        )
        out = re.sub(
            r"\b(tendr[ií]as? que |tendr[ií]a que |usted )?separarse con\b",
            r"\1pagar",
            out,
            flags=re.I,
        )
        out = re.sub(r"\bsepararte de un buen\b", "pagar un buen", out, flags=re.I)
        out = re.sub(r"\bsepararse de un buen\b", "pagar un buen", out, flags=re.I)

    # patron deities → "mecenas" es mal sentido (sponsor); preferir patrono/a
    if re.search(r"\bpatron deities\b", en_l) or re.search(r"\bpatron deity\b", en_l):
        out = re.sub(r"\bdeidades mecenas\b", "deidades patronas", out, flags=re.I)
        out = re.sub(r"\bmecenas menores\b", "patronas menores", out, flags=re.I)

    # Puntuación ES
    out = re.sub(r"\s+([!?.,;:])", r"\1", out)
    out = re.sub(r"([¿¡])\s+", r"\1", out)
    if "?" in en and "?" in out and "¿" not in out:
        # insertar ¿ al inicio de la última pregunta si falta
        out = re.sub(r"(^|[.!] )([^¿?]+\?)", r"\1¿\2", out, count=1)
    out = re.sub(r" {2,}", " ", out)
    return out.strip()
