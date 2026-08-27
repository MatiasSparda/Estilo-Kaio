"""Formato de nombres propios: English (traducción) + polish ES de guías."""

from __future__ import annotations

import re

# Glosas frecuentes en walkthroughs EN→ES (sin lógica de juego).
_GLOSS_HINTS: dict[str, str] = {
    "Brother Emblem": "Emblema Hermano",
    "Tune of Currents": "Melodía de las Corrientes",
    "Tune of Echoes": "Melodía de los Ecos",
    "Tune of Ages": "Melodía de las Eras",
    "Pegasus Seeds": "Semillas Pegaso",
    "Switch Hook": "Gancho Cambiador",
    "Long Hook": "Gancho Largo",
    "Rock Brisket": "Filete de Roca",
    "Goron Vase": "Jarrón Goron",
    "Goronade": "Goronade",
    "Lava Juice": "Jugo de Lava",
    "Mermaid Key": "Llave Sirena",
    "Old Mermaid Key": "Llave Sirena Antigua",
    "Crown Key": "Llave Corona",
    "Crown Dungeon": "Mazmorra de la Corona",
    "Rolling Ridge": "Cordillera Rodante",
    "Talus Peaks": "Picos Talus",
    "Crazy Carts": "Crazy Carts",
    "Target Carts": "Target Carts",
    "Big Bang": "Big Bang",
    "Graceful Goron": "Goron Elegante",
    "Power Bracelet": "Brazalete de Fuerza",
    "Roc's Feather": "Pluma de Roc",
    "Seed Shooter": "Lanzador de Semillas",
    "Maku Tree": "Árbol Maku",
}

_PROPER_RE = re.compile(
    r"\b("
    r"[A-Z][a-z]+(?:\s+(?:of|the|and)\s+[A-Z][a-z]+)+"
    r"|"
    r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+"
    r")\b"
)

_TUNE_NAME_RE = re.compile(
    r"\bTune of (Currents|Echoes|Ages)\b",
    flags=re.I,
)


def extract_proper_nouns(english_text: str) -> list[str]:
    text = english_text or ""
    found: list[str] = []
    seen: set[str] = set()
    for en in sorted(_GLOSS_HINTS.keys(), key=len, reverse=True):
        if en.lower() in text.lower() and en.lower() not in seen:
            found.append(en)
            seen.add(en.lower())
    for m in _PROPER_RE.finditer(text):
        name = m.group(1).strip()
        if name.lower() in seen:
            continue
        if name.lower() in {"the present", "the past", "once again", "make your"}:
            continue
        if len(name) < 6:
            continue
        found.append(name)
        seen.add(name.lower())
    return found


def _gloss_for(en: str) -> str:
    if en in _GLOSS_HINTS:
        return _GLOSS_HINTS[en]
    m = _TUNE_NAME_RE.fullmatch((en or "").strip())
    if m:
        key = f"Tune of {m.group(1).capitalize()}"
        if key in _GLOSS_HINTS:
            return _GLOSS_HINTS[key]
    # Offline: Gemma/LiteRT si está arriba; si no, dejar EN
    try:
        from .gemma_translate import is_server_running, translate_text

        if is_server_running():
            gloss = translate_text(en, "en", "es", timeout=20.0, max_tokens=64, review=False)
            gloss = (gloss or "").strip()
            if gloss and gloss.lower() != en.lower() and not gloss.startswith("["):
                return gloss
    except Exception:
        pass
    return en

def _fold(s: str) -> str:
    import unicodedata

    s = (s or "").lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _find_folded_span(text: str, needle: str) -> tuple[int, int] | None:
    """Índices [start, end) en text cuya forma folded coincide con needle folded."""
    if not text or not needle:
        return None
    import unicodedata

    t_fold = []
    map_idx = []
    for i, ch in enumerate(text):
        norm = unicodedata.normalize("NFD", ch.lower())
        for c in norm:
            if unicodedata.category(c) != "Mn":
                t_fold.append(c)
                map_idx.append(i)
    folded = "".join(t_fold)
    n = _fold(needle)
    pos = folded.find(n)
    if pos < 0:
        return None
    start = map_idx[pos]
    end_pos = pos + len(n) - 1
    end = map_idx[end_pos] + 1
    return start, end


def _canon_tune(name: str) -> str:
    m = re.search(r"Tune of (Currents|Echoes|Ages)", name, flags=re.I)
    if not m:
        return name
    return f"Tune of {m.group(1).capitalize()}"


def _fix_play_tune_leftovers(out: str, en: str) -> str:
    """
    Corrige calcos / inglés residual:
    - Play the Tune of X (…cualquier…) → Toca Tune of X (glosa)
    - Juega … Tune of X …
    """
    text = out

    def _toca_name(raw_name: str) -> str:
        name = _canon_tune(raw_name)
        gloss = _GLOSS_HINTS.get(name) or _gloss_for(name)
        return f"Toca {name} ({gloss})"

    # Play/Juega the Tune of X (parens opcionales) — sin comer el resto de la oración
    text = re.sub(
        r"\b(?:Play|Juega(?:r)?|Juegue(?:n)?)\s+(?:the\s+)?(Tune of (?:Currents|Echoes|Ages))"
        r"(?:\s*\([^)]*\))?",
        lambda m: _toca_name(m.group(1)),
        text,
        flags=re.I,
    )

    # Toca Tune… pero glosa basura tipo (Toca la melodía…)
    text = re.sub(
        r"\bToca\s+(Tune of (?:Currents|Echoes|Ages))\s*\((?:Toca|Play|Juega)[^)]*\)",
        lambda m: _toca_name(m.group(1)),
        text,
        flags=re.I,
    )

    # Melodía de Echoes / Currents / Ages (mezcla EN residual, sin English primero)
    for suffix, key in (
        ("Currents", "Tune of Currents"),
        ("Echoes", "Tune of Echoes"),
        ("Ages", "Tune of Ages"),
    ):
        gloss = _GLOSS_HINTS[key]
        text = re.sub(
            rf"(?<!\()\bMelod[ií]a de {re.escape(suffix)}\b(?!\s*\()",
            f"{key} ({gloss})",
            text,
            flags=re.I,
        )

    # Si el EN pide Play the Tune y el ES aún arranca en inglés Play
    if re.search(r"\bplay\s+the\s+tune\b", en, flags=re.I) and re.match(
        r"^\s*Play\b", text
    ):
        text = re.sub(r"^\s*Play\s+the\s+", "Toca ", text, count=1, flags=re.I)

    return text


def _fix_guided_calques(out: str, en: str) -> str:
    """Calcos frecuentes guiados por el inglés fuente."""
    text = out
    en_l = en.lower()

    # vine ≠ wine
    if re.search(r"\bvines?\b", en_l):
        def _vine_repl(m: re.Match) -> str:
            return f"{m.group(1)} de enredadera"

        text = re.sub(
            r"\b(cubiert(?:a|o|as|os))\s+de\s+vino\b",
            _vine_repl,
            text,
            flags=re.I,
        )
        text = re.sub(r"\bde\s+vino\b", "de enredadera", text, flags=re.I)
        text = re.sub(
            r"\bvino[- ]cubiert([ao]s?)",
            r"cubiert\1 de enredadera",
            text,
            flags=re.I,
        )

    if re.search(r"\bindents?\b", en_l):
        text = re.sub(r"\bindentado\b", "hueco", text, flags=re.I)
        text = re.sub(r"\bindentaci[oó]n\b", "hueco", text, flags=re.I)

    if "plant bulb" in en_l or "bulb" in en_l:
        text = re.sub(r"\bbulbo de planta\b", "tallo de planta", text, flags=re.I)

    if "signpost" in en_l:
        text = re.sub(r"\bposte de se[nñ]alizaci[oó]n\b", "poste indicador", text, flags=re.I)

    return text


def _fix_spanish_grammar(out: str) -> str:
    text = out
    text = re.sub(r"\bal cueva\b", "a la cueva", text, flags=re.I)
    text = re.sub(r"\bdel cueva\b", "de la cueva", text, flags=re.I)
    text = re.sub(r"\by\s+(inund)", r"e \1", text, flags=re.I)
    text = re.sub(r"\bunas cuantos\b", "unas cuantas", text, flags=re.I)
    text = re.sub(r"\bunos cuantas\b", "unos cuantos", text, flags=re.I)
    text = re.sub(r"\bla [aá]rea\b", "el área", text, flags=re.I)
    text = re.sub(r"\bvuelve al cueva\b", "vuelve a la cueva", text, flags=re.I)
    # Artículo delante de nombre EN propio
    text = re.sub(
        r"\b(Toca|Usa|Utiliza|Reproduce)\s+(?:la|el)\s+(?=Tune of|[A-Z])",
        r"\1 ",
        text,
    )
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def polish_spanish_guide(text: str, english_source: str = "") -> str:
    """Corrige calcos típicos EN→ES en walkthroughs."""
    if not text:
        return text
    out = text
    en = english_source or ""

    # Play + Tune/Song/Melody → Toca (nunca Juega) — genérico
    musical = bool(
        re.search(r"\b(play|tune|song|melody|ocarina|harp)\b", en, flags=re.I)
        or re.search(r"\b(tune of|melod[ií]a|canci[oó]n)\b", out, flags=re.I)
    )
    if musical:
        out = re.sub(
            r"\bJuega(?:r)?\s+(?:la|el|las|los)?\s*",
            "Toca ",
            out,
            flags=re.I,
        )
        out = re.sub(
            r"\bJuegue(?:n)?\s+(?:la|el)?\s*",
            "Toque ",
            out,
            flags=re.I,
        )

    out = _fix_play_tune_leftovers(out, en)
    out = _fix_guided_calques(out, en)
    out = _fix_spanish_grammar(out)
    return out


def apply_proper_noun_format(english_source: str, translated: str) -> str:
    """
    Asegura 'English (Traducción)' en el texto traducido.
    - Si ya está English (...), no toca (salvo glosa basura: se repara en polish).
    - Si solo está la glosa ES, la reemplaza por English (glosa).
    """
    text = translated or ""
    if not text or not (english_source or "").strip():
        return text

    nouns = extract_proper_nouns(english_source)
    for en in sorted(nouns, key=len, reverse=True):
        gloss = _gloss_for(en)
        # Ya tiene English (…): si la glosa empieza con verbo, dejarla a polish
        if re.search(re.escape(en) + r"\s*\(", text):
            continue
        if re.search(r"\b" + re.escape(en) + r"\b", text):
            text = re.sub(
                r"\b" + re.escape(en) + r"\b(?!\s*\()",
                f"{en} ({gloss})",
                text,
                count=1,
            )
            continue
        if gloss.lower() == en.lower():
            continue
        span = _find_folded_span(text, gloss)
        if span:
            a, b = span
            text = text[:a] + f"{en} ({gloss})" + text[b:]
    return text
