"""Particionado heurístico de guías + verificación de citas."""

from __future__ import annotations

import re
from dataclasses import dataclass

SHORT_GUIDE_CHARS = 8000
SHORT_SECTION_CHARS = 400

# Prefijos que marcan una sección real (no metadatos tipo PASOS/UBICACIÓN)
STRONG_PREFIXES = (
    "mission",
    "misión",
    "mision",
    "quest",
    "chapter",
    "capítulo",
    "capitulo",
    "boss",
    "jefe",
    "part",
    "parte",
    "area",
    "área",
    "walkthrough",
    "consejos",
    "tips",
    "hint",
    "pistas",
)

# Nunca son headings por sí solos
NEVER_HEADING = {
    "pasos",
    "steps",
    "paso",
    "ubicación",
    "ubicacion",
    "location",
    "nivel",
    "level",
    "equipo",
    "equipment",
    "recompensa",
    "reward",
    "notas",
    "notes",
}


@dataclass
class GuideSection:
    id: int  # 1-based
    title: str
    body: str


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def citation_in_source(citation: str, source: str) -> bool:
    cite = normalize_whitespace(citation).strip().strip('"').strip("'")
    body = normalize_whitespace(source)
    if len(cite) < 8:
        return False
    cite_l = cite.lower()
    body_l = body.lower()
    if cite_l in body_l:
        return True
    # Modelos a veces citan con puntos/comillas de más: probar ventanas
    if len(cite) >= 32:
        for i in range(0, len(cite) - 31, 8):
            chunk = cite_l[i : i + 32]
            if chunk in body_l:
                return True
    return False


def extract_fuente_line(response: str) -> str | None:
    if not response:
        return None
    # Línea típica; también acepta "Fuente:" / 'FUENTE:' / Fuente :
    for line in response.splitlines():
        stripped = line.strip().strip('"').strip("'")
        m = re.match(r"^\s*FUENTE\s*:\s*(.+)$", stripped, flags=re.IGNORECASE)
        if m:
            cite = m.group(1).strip().strip('"').strip("'").strip("<>").strip()
            return cite or None
    # Fallback: aparece en cualquier parte del texto
    m = re.search(r"FUENTE\s*:\s*(.+)", response, flags=re.IGNORECASE)
    if m:
        cite = m.group(1).strip().strip('"').strip("'").strip("<>").strip()
        # cortar si el modelo sigue escribiendo
        cite = cite.split("\n")[0].strip().strip('"').strip("'").strip("<>").strip()
        return cite or None
    return None


def extract_felipe_line(response: str) -> str | None:
    if not response:
        return None
    for line in response.splitlines():
        stripped = line.strip().strip('"').strip("'")
        m = re.match(r"^\s*FELIPE\s*:\s*(.+)$", stripped, flags=re.IGNORECASE)
        if m:
            tip = m.group(1).strip().strip('"').strip("'").strip()
            return tip or None
    m = re.search(r"FELIPE\s*:\s*(.+)", response, flags=re.IGNORECASE)
    if m:
        tip = m.group(1).strip().split("\n")[0].strip().strip('"').strip("'").strip()
        return tip or None
    return None


def strip_fuente_from_steps(response: str) -> str:
    lines = []
    for line in (response or "").splitlines():
        stripped = line.strip().strip('"').strip("'")
        if re.match(r"^\s*FUENTE\s*:", stripped, flags=re.IGNORECASE):
            continue
        if re.match(r"^\s*FELIPE\s*:", stripped, flags=re.IGNORECASE):
            continue
        lines.append(line)
    text = "\n".join(lines).strip()
    text = re.sub(r'\n?["\']?\s*FUENTE\s*:.*$', "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r'\n?["\']?\s*FELIPE\s*:.*$', "", text, flags=re.IGNORECASE).strip()
    return text


def strip_felipe_from_steps(response: str) -> str:
    """Alias: strip_fuente también saca FELIPE."""
    return strip_fuente_from_steps(response)


def _is_separator(line: str) -> bool:
    s = line.strip()
    if len(s) < 3:
        return False
    return bool(re.fullmatch(r"[\-=_*─═]{3,}", s))


def _letter_ratio_upper(s: str) -> bool:
    letters = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", s)
    return bool(letters) and letters.upper() == letters and len(letters) >= 4


def _is_heading(line: str, next_line: str | None) -> bool:
    s = line.strip()
    if not s or len(s) > 120:
        return False
    if _is_separator(s):
        return False

    # Markdown
    if re.match(r"^#{1,3}\s+\S", s):
        return True

    lower = s.lower().rstrip(":")
    first_token = re.split(r"[\s:]+", lower, maxsplit=1)[0]
    if first_token in NEVER_HEADING:
        return False

    # Prefijos fuertes: "MISIÓN:", "QUEST ", "Boss:", etc.
    for prefix in STRONG_PREFIXES:
        if lower.startswith(prefix + ":") or lower.startswith(prefix + " "):
            return True
        if lower == prefix:
            return True

    # Título corto + separador debajo (===)
    if next_line and _is_separator(next_line) and 3 <= len(s) <= 100:
        return True

    # MAYÚSCULAS solo si hay separador debajo (título de bloque)
    if _letter_ratio_upper(s) and len(s) <= 90:
        if next_line and _is_separator(next_line):
            return True

    # Part 1 / Parte 2
    if re.match(r"^(part|parte)\s+\d+\b", lower):
        return True

    return False


def _clean_title(line: str) -> str:
    s = line.strip()
    s = re.sub(r"^#{1,3}\s+", "", s)
    return s.strip() or "Sin título"


def parse_guide_sections(guide_text: str) -> list[GuideSection]:
    text = guide_text or ""
    if not text.strip():
        return [GuideSection(id=1, title="Guía completa", body="")]

    lines = text.splitlines()
    heading_idxs: list[int] = []

    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if _is_separator(line):
            continue
        if _is_heading(line, nxt):
            heading_idxs.append(i)

    heading_idxs = sorted(set(heading_idxs))

    if not heading_idxs:
        return [GuideSection(id=1, title="Guía completa", body=text.strip())]

    sections: list[GuideSection] = []

    # Prefacio
    if heading_idxs[0] > 0:
        preface = "\n".join(lines[: heading_idxs[0]]).strip()
        if preface and len(preface) > 40:
            sections.append(GuideSection(id=0, title="Introducción", body=preface))

    for n, start in enumerate(heading_idxs):
        end = heading_idxs[n + 1] if n + 1 < len(heading_idxs) else len(lines)
        title = _clean_title(lines[start])
        body = "\n".join(lines[start:end]).strip()
        sections.append(GuideSection(id=0, title=title, body=body))

    for i, sec in enumerate(sections, start=1):
        sec.id = i

    sections = _merge_tiny_sections(sections)

    for i, sec in enumerate(sections, start=1):
        sec.id = i

    return sections or [GuideSection(id=1, title="Guía completa", body=text.strip())]


def _merge_tiny_sections(sections: list[GuideSection]) -> list[GuideSection]:
    """Fusiona encabezados banner (casi sin cuerpo) con la sección siguiente."""
    if len(sections) <= 1:
        return sections
    merged: list[GuideSection] = []
    i = 0
    while i < len(sections):
        cur = sections[i]
        content = _body_content_len(cur)
        if content == 0 and i + 1 < len(sections):
            nxt = sections[i + 1]
            title = f"{cur.title} — {nxt.title}"
            body = f"{cur.body}\n\n{nxt.body}".strip()
            merged.append(GuideSection(id=0, title=title, body=body))
            i += 2
            continue
        merged.append(cur)
        i += 1
    return merged


def _body_content_len(section: GuideSection) -> int:
    """Caracteres de cuerpo ignorando título y separadores."""
    lines = []
    title = section.title.strip()
    for line in section.body.splitlines():
        s = line.strip()
        if not s or _is_separator(s):
            continue
        if s == title or title.startswith(s) or s.startswith(title[:20]):
            continue
        lines.append(s)
    return len(" ".join(lines))


def is_long_guide(guide_text: str) -> bool:
    return len(guide_text or "") > SHORT_GUIDE_CHARS


def build_context_for_section(
    sections: list[GuideSection],
    section_id: int,
    *,
    following: int = 0,
) -> str:
    """
    Contexto de la sección elegida.
    following>0: incluye las N secciones siguientes (útil para “qué hago ahora”).
    Si la sección es muy corta, también suma ±1 vecina como antes.
    """
    by_id = {s.id: s for s in sections}
    if section_id not in by_id:
        return "\n\n".join(s.body for s in sections)

    chosen = by_id[section_id]
    parts = [chosen.body]
    follow_n = max(0, int(following or 0))
    for offset in range(1, follow_n + 1):
        nxt = by_id.get(section_id + offset)
        if nxt:
            parts.append(nxt.body)

    if len(chosen.body) < SHORT_SECTION_CHARS:
        if section_id - 1 in by_id:
            prev = by_id[section_id - 1].body
            if prev not in parts:
                parts.insert(0, prev)
        if follow_n == 0 and section_id + 1 in by_id:
            nxt = by_id[section_id + 1].body
            if nxt not in parts:
                parts.append(nxt)
    return "\n\n".join(parts)


def filter_sections_by_query(
    sections: list[GuideSection], query: str
) -> list[GuideSection]:
    q = (query or "").strip().lower()
    if not q:
        return sections
    return [s for s in sections if q in s.title.lower()]


# --- Recuperación de sección (ES↔EN básico + anti-intro) ---

_META_TITLE_RE = re.compile(
    r"(introduction|introducci[oó]n|contents|table of|\bindex\b|versi[oó]n|"
    r"copyright|credits|bosses|faq|spoiler|legales?|appendix|ap[eé]ndice|"
    r"controls|controles|-=\s*\d+\.\s*introduction)",
    re.I,
)

_GENERIC_TITLE_RE = re.compile(
    r"^(past|present|pasado|presente)(\s*[—\-:].*)?$",
    re.I,
)

_STOPWORDS = {
    "que",
    "qué",
    "como",
    "cómo",
    "donde",
    "dónde",
    "para",
    "por",
    "con",
    "una",
    "uno",
    "los",
    "las",
    "del",
    "the",
    "and",
    "for",
    "what",
    "where",
    "next",
    "hacer",
    "acabo",
    "superar",
    "terminar",
    "despues",
    "después",
    "ahora",
    "saber",
}

# Aliases cortos ES → términos típicos de guías EN
_TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "corona": ("crown",),
    "mazmorra": ("dungeon", "cave"),
    "baile": ("dance",),
    "goron": ("goron",),
    "sirena": ("mermaid",),
    "cordillera": ("ridge", "rolling"),
    "ruleta": ("rolling", "ridge"),
    "emblema": ("emblem",),
    "hermandad": ("brother", "emblem"),
    "filete": ("brisket",),
    "roca": ("rock", "brisket"),
    "vagoneta": ("cart", "target"),
    "llave": ("key",),
    "cascada": ("waterfall",),
    "pasado": ("past",),
    "presente": ("present",),
    "cueva": ("cave",),
    "melodia": ("tune", "currents"),
    "melodía": ("tune", "currents"),
    "corrientes": ("currents", "tune"),
    "gancho": ("hook", "switch"),
    "pegaso": ("pegasus",),
}

_TERM_WEIGHTS: dict[str, int] = {
    "crown": 5,
    "corona": 5,
    "goron": 4,
    "dance": 4,
    "baile": 4,
    "mermaid": 5,
    "sirena": 5,
    "emblem": 4,
    "brother": 4,
    "brisket": 5,
    "ridge": 3,
    "rolling": 3,
    "dungeon": 2,
    "mazmorra": 2,
    "cave": 1,
    "past": 1,
    "present": 1,
    "pasado": 1,
    "presente": 1,
    "key": 2,
}

# Términos frecuentes en toda la guía: sirven para rankear, no para anclar progreso
_PROGRESS_FILLER_TERMS = {
    "goron",
    "ridge",
    "rolling",
    "past",
    "present",
    "pasado",
    "presente",
    "cave",
    "cueva",
    "key",
    "llave",
}


def is_meta_section(section: GuideSection) -> bool:
    return bool(_META_TITLE_RE.search(section.title or ""))


def is_generic_title_section(section: GuideSection) -> bool:
    title = (section.title or "").strip()
    if is_meta_section(section):
        return True
    # "Past", "Present", "Past — ..." demasiado genérico sin área
    base = re.sub(r"\s*[—\-:].*$", "", title).strip()
    if _GENERIC_TITLE_RE.match(title) or base.lower() in {
        "past",
        "present",
        "pasado",
        "presente",
    }:
        # Permitir "Present — Rolling Ridge"
        if "ridge" in title.lower() or "goron" in title.lower() or "dungeon" in title.lower():
            return False
        if "—" in title or " - " in title or ":" in title:
            rest = re.split(r"[—\-:]", title, maxsplit=1)[-1].strip()
            if len(rest) >= 4 and rest.lower() not in {"past", "present"}:
                return False
        return True
    return False


def query_search_terms(query: str) -> list[str]:
    raw = re.findall(r"[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]{3,}", query or "")
    terms: set[str] = set()
    for token in raw:
        t = token.lower()
        if t in _STOPWORDS:
            continue
        terms.add(t)
        for alias in _TERM_ALIASES.get(t, ()):
            terms.add(alias.lower())
    return sorted(terms, key=len, reverse=True)


def score_section_for_terms(section: GuideSection, terms: list[str]) -> int:
    if not terms:
        return 0
    blob = f"{section.title}\n{section.body}".lower()
    title_l = (section.title or "").lower()
    hits: list[str] = []
    score = 0
    for t in terms:
        if t not in blob:
            continue
        w = _TERM_WEIGHTS.get(t, 1)
        if t in title_l:
            w += 2
        score += w
        hits.append(t)

    place = {"crown", "corona", "dungeon", "mazmorra", "ridge", "rolling"}
    actor = {"goron", "dance", "baile", "mermaid", "sirena", "emblem", "brother", "brisket"}
    if any(t in place for t in hits) and any(t in actor for t in hits):
        score += 5
    return score


def rank_sections_for_query(
    sections: list[GuideSection], query: str
) -> list[tuple[int, GuideSection]]:
    terms = query_search_terms(query)
    if not terms:
        return []
    ranked: list[tuple[int, GuideSection]] = []
    for s in sections:
        if is_generic_title_section(s):
            continue
        sc = score_section_for_terms(s, terms)
        if sc > 0:
            ranked.append((sc, s))
    ranked.sort(key=lambda x: (x[0], x[1].id), reverse=True)
    return ranked


def find_appendix_start_id(sections: list[GuideSection]) -> int:
    """Primer id de apéndice (Bosses/Items/…) tras el walkthrough principal."""
    for s in sections:
        title = (s.title or "").strip()
        m = re.match(r"-=\s*(\d+)\.", title)
        if m and int(m.group(1)) >= 6:
            return s.id
        if re.search(r"\bbosses\b", title, re.I) and s.id > 40:
            return s.id
    if not sections:
        return 0
    return sections[-1].id + 1


def is_walkthrough_section(section: GuideSection, appendix_start_id: int) -> bool:
    if section.id >= appendix_start_id:
        return False
    if is_meta_section(section) or is_generic_title_section(section):
        return False
    title = (section.title or "").strip()
    if re.match(r"-=\s*\d+\.", title):
        return False
    return True


def resolve_progress_start_id(sections: list[GuideSection], query: str) -> int | None:
    """
    Para 'acabo de superar X': ubica el hito MÁS TARDÍO del walkthrough que
    mencione los términos distintivos de la pregunta (no el más temprano).
    Así la ventana forward cubre 'qué sigue', no el inicio del área.
    """
    if not sections:
        return None
    appendix = find_appendix_start_id(sections)
    terms = query_search_terms(query)
    # Eventos concretos (dance/corona/…), no fillers tipo goron/ridge
    distinctive = [
        t
        for t in terms
        if _TERM_WEIGHTS.get(t, 1) >= 3 and t not in _PROGRESS_FILLER_TERMS
    ]
    if not distinctive:
        distinctive = [t for t in terms if t not in _PROGRESS_FILLER_TERMS][:6]
    if not distinctive:
        distinctive = terms[:4]

    last_by_term: dict[str, int] = {}
    for s in sections:
        if not is_walkthrough_section(s, appendix):
            continue
        blob = f"{s.title}\n{s.body}".lower()
        for t in distinctive:
            if t in blob:
                last_by_term[t] = s.id

    # Frases compuestas (corona+mazmorra → crown dungeon) anclan mejor
    q_l = (query or "").lower()
    if ("corona" in q_l or "crown" in q_l) and (
        "mazmorra" in q_l or "dungeon" in q_l
    ):
        for s in sections:
            if not is_walkthrough_section(s, appendix):
                continue
            blob = f"{s.title}\n{s.body}".lower()
            if "crown dungeon" in blob or (
                "crown" in blob and "dungeon" in blob
            ):
                last_by_term["crown_dungeon"] = s.id

    if last_by_term:
        last = max(last_by_term.values())
        # El jugador ya completó ese hito → mirar la sección siguiente
        walk_ids = [
            s.id for s in sections if is_walkthrough_section(s, appendix)
        ]
        if last in walk_ids:
            idx = walk_ids.index(last)
            if idx + 1 < len(walk_ids):
                return walk_ids[idx + 1]
        return last

    ranked = [
        (sc, s)
        for sc, s in rank_sections_for_query(sections, query)
        if is_walkthrough_section(s, appendix)
    ]
    if not ranked:
        return None
    top = ranked[0][0]
    cluster = [s for sc, s in ranked if sc >= max(1, top - 4)]
    return max(s.id for s in cluster)


def resolve_auto_section_id(
    sections: list[GuideSection],
    query: str,
    llm_pick: int | None,
    *,
    prefer_later: bool = False,
) -> int | None:
    """
    Combina match por términos + pick del LLM.
    Evita intros/TOC/títulos genéricos.
    Si prefer_later (progreso): ancla en el hito más tardío del walkthrough.
    """
    by_id = {s.id: s for s in sections}
    ranked = rank_sections_for_query(sections, query)

    def usable(sid: int | None) -> bool:
        if sid is None or sid not in by_id:
            return False
        return not is_generic_title_section(by_id[sid])

    if prefer_later:
        progress_id = resolve_progress_start_id(sections, query)
        if progress_id is not None:
            return progress_id

    if ranked and ranked[0][0] >= 4:
        best_id = ranked[0][1].id
        if usable(llm_pick):
            llm_score = score_section_for_terms(
                by_id[llm_pick], query_search_terms(query)
            )
            if llm_score >= ranked[0][0]:
                return llm_pick
        return best_id

    if usable(llm_pick):
        return llm_pick
    if ranked:
        return ranked[0][1].id
    return llm_pick if usable(llm_pick) else None


def build_forward_context(
    sections: list[GuideSection],
    start_id: int,
    *,
    max_chars: int = 10000,
    lookback: int = 0,
) -> str:
    """Desde start_id (con lookback opcional) hacia adelante hasta max_chars."""
    ids = [s.id for s in sections]
    if not ids:
        return ""
    start_idx = 0
    for i, s in enumerate(sections):
        if s.id >= start_id:
            start_idx = i
            break
    start_idx = max(0, start_idx - max(0, lookback))

    parts: list[str] = []
    total = 0
    for s in sections[start_idx:]:
        chunk = s.body or ""
        if parts and total + len(chunk) > max_chars:
            remain = max_chars - total
            if remain > 400:
                parts.append(chunk[:remain])
            break
        parts.append(chunk)
        total += len(chunk)
        if total >= max_chars:
            break
    return "\n\n".join(parts).strip()


def build_progress_context(
    sections: list[GuideSection],
    start_id: int,
    *,
    max_chars: int = 12000,
    lookback: int = 1,
) -> str:
    """Ventana alrededor del hito de progreso (lookback + forward)."""
    wide = build_forward_context(
        sections,
        start_id,
        max_chars=max(max_chars * 2, 20000),
        lookback=lookback,
    )
    if not wide:
        return wide
    return wide[:max_chars].strip()


def build_progress_candidate_contexts(
    sections: list[GuideSection],
    query: str,
    *,
    max_chars: int = 12000,
    max_candidates: int = 3,
) -> list[tuple[int, str]]:
    """
    Varias ventanas candidatas (hito principal + otras secciones fuertes),
    para reintentar locate si la primera falla.
    """
    appendix = find_appendix_start_id(sections)
    primary = resolve_progress_start_id(sections, query)
    starts: list[int] = []
    if primary is not None:
        starts.append(primary)

    ranked = [
        (sc, s)
        for sc, s in rank_sections_for_query(sections, query)
        if is_walkthrough_section(s, appendix)
    ]
    # Preferir ids más tardíos entre los bien rankeados
    for sc, s in sorted(ranked, key=lambda x: (x[0], x[1].id), reverse=True):
        if s.id not in starts:
            starts.append(s.id)
        if len(starts) >= max_candidates:
            break

    out: list[tuple[int, str]] = []
    seen_hash: set[str] = set()
    for sid in starts[:max_candidates]:
        ctx = build_progress_context(
            sections, sid, max_chars=max_chars, lookback=1
        )
        if not ctx:
            continue
        key = ctx[:240]
        if key in seen_hash:
            continue
        seen_hash.add(key)
        out.append((sid, ctx))
    return out


def _split_paragraphs(text: str) -> list[str]:
    raw = (text or "").replace("\r\n", "\n")
    parts = re.split(r"\n\s*\n+", raw)
    out = []
    for p in parts:
        cleaned = normalize_whitespace(p)
        if len(cleaned) >= 20:
            out.append(cleaned)
    if out:
        return out
    # Fallback: trozos por oraciones si no hay párrafos
    sentences = re.split(r"(?<=[.!?])\s+", normalize_whitespace(text))
    return [s.strip() for s in sentences if len(s.strip()) >= 20]


def resolve_literal_guide_sentence(guide_text: str, approx: str) -> str | None:
    """
    Dada una oración aproximada (posiblemente limpiada), devuelve la oración
    literal del guide_text que mejor la contiene.
    """
    body = guide_text or ""
    approx = normalize_whitespace(approx or "")
    if not body or len(approx) < 16:
        return None
    idx = find_anchor_in_text(body, approx)
    if idx >= 0:
        return _sentence_at(body, idx) or approx

    body_l = body.lower()
    approx_l = approx.lower()
    # Ventanas deslizantes: sobrevive a parafraseos leves al inicio/fin
    for win in (64, 48, 36, 28):
        if len(approx_l) < win:
            continue
        step = max(4, win // 6)
        for offset in range(0, len(approx_l) - win + 1, step):
            chunk = approx_l[offset : offset + win]
            if chunk.count(" ") < 3:
                continue
            pos = body_l.find(chunk)
            if pos >= 0:
                return _sentence_at(body, pos)

    words = re.findall(r"[A-Za-z']{3,}", approx)
    if len(words) < 5:
        return None
    for length in range(min(8, len(words)), 4, -1):
        for i in range(0, len(words) - length + 1):
            # Reconstruir con ' of/the/to ' aproximado buscando solo las palabras clave
            needle = " ".join(words[i : i + length]).lower()
            # Buscar secuencia de palabras en orden (regex flexible)
            parts = [re.escape(w) for w in words[i : i + length]]
            pat = r"\b" + r"\b.{0,16}\b".join(parts) + r"\b"
            m = re.search(pat, body, flags=re.I | re.S)
            if m:
                return _sentence_at(body, m.start())
    return None


def _sentence_at(text: str, idx: int) -> str | None:
    """Oración completa en idx; los saltos de línea NO cortan (guías con wrap)."""
    if idx < 0 or not text:
        return None
    # Inicio: después del .!? anterior (ignorar \\n de wrap)
    start = idx
    while start > 0 and text[start - 1] not in ".!?":
        start -= 1
    while start < len(text) and text[start].isspace():
        start += 1
    end = idx
    while end < len(text) and text[end] not in ".!?":
        end += 1
    if end < len(text) and text[end] in ".!?":
        end += 1
    sent = normalize_whitespace(text[start:end])
    # Evitar cortar en encabezados siguientes (= / ---)
    sent = re.sub(r"\s*=+\s*.*$", "", sent).strip()
    sent = re.sub(r"\s*-{3,}.*$", "", sent).strip()
    return sent if len(sent) >= 16 else None


def find_anchor_in_text(fragment: str, anchor: str) -> int:
    """Índice del ancla en el fragmento (tolerant a whitespace)."""
    frag = fragment or ""
    anc = (anchor or "").strip()
    if not frag or not anc:
        return -1
    idx = frag.find(anc)
    if idx >= 0:
        return idx
    # Normalizado
    frag_n = normalize_whitespace(frag).lower()
    anc_n = normalize_whitespace(anc).lower()
    pos = frag_n.find(anc_n)
    if pos < 0 and len(anc_n) >= 24:
        # ventana del ancla
        pos = frag_n.find(anc_n[:24])
    if pos < 0:
        return -1
    # Mapear aprox al texto original (best-effort: buscar prefijo)
    needle = anc.strip()[:32]
    return frag.lower().find(needle.lower())


def _clean_guide_sentence(sentence: str) -> str:
    """Quita adornos de borde (====, ----) sin romper citas literales del cuerpo."""
    s = (sentence or "").strip()
    # Solo bordes / títulos decorativos, no reescribir el medio
    s = re.sub(r"^[\s=\-_—]+", "", s)
    s = re.sub(r"[\s=\-_—]+$", "", s)
    s = normalize_whitespace(s)
    if len(s) < 18:
        return ""
    letters = len(re.findall(r"[A-Za-zÁÉÍÓÚáéíóúüñ]", s))
    deco = len(re.findall(r"[=_\-—]", s))
    if letters < 18 or deco > letters:
        return ""
    # Título de zona sin verbo de acción
    if re.match(
        r"^(past|present|pasado|presente)\b.{0,50}$",
        s,
        re.I,
    ) and not re.search(
        r"\b(go|enter|talk|use|head|walk|return|speak|climb|jump|open)\b",
        s,
        re.I,
    ):
        return ""
    return s


def _guide_sentences(text: str) -> list[str]:
    raw = (text or "").replace("\r\n", "\n")
    # Separar encabezados decorativos para que no se peguen a la prosa
    raw = re.sub(r"\n\s*=+\s*\n", ".\n", raw)
    raw = re.sub(r"\n\s*-{4,}\s*\n", ".\n", raw)
    raw = re.sub(
        r"(?i)\b(past|present|pasado|presente)\s*=+\s*",
        r". \1: ",
        raw,
    )
    raw = re.sub(r"={3,}", " ", raw)
    raw = re.sub(r"-{4,}", " ", raw)
    raw = normalize_whitespace(raw)
    parts = re.split(r"(?<=[.!?])\s+", raw)
    out: list[str] = []
    for p in parts:
        cleaned = _clean_guide_sentence(p.strip())
        if cleaned:
            out.append(cleaned)
    return out


def locate_anchor_by_terms(fragment: str, query: str) -> str | None:
    """
    Fallback sin LLM: última oración del fragmento que matchee los términos
    distintivos; el ancla es la oración SIGUIENTE (qué viene después).
    """
    body = _strip_progress_header_if_any(fragment)
    if not body:
        return None
    terms = [
        t
        for t in query_search_terms(query)
        if _TERM_WEIGHTS.get(t, 1) >= 3 and t not in _PROGRESS_FILLER_TERMS
    ]
    if not terms:
        terms = [t for t in query_search_terms(query) if t not in _PROGRESS_FILLER_TERMS][:5]
    if not terms:
        return None

    sentences = _guide_sentences(body)
    if not sentences:
        return None

    last_i = -1
    for i, s in enumerate(sentences):
        low = s.lower()
        score = sum(_TERM_WEIGHTS.get(t, 1) for t in terms if t in low)
        if score > 0:
            last_i = i

    if last_i < 0:
        return None

    # Preferir la oración inmediata posterior al último hito matcheado
    idx = last_i + 1 if last_i + 1 < len(sentences) else last_i
    cite = sentences[idx]
    if citation_in_source(cite, body):
        return cite
    for n in (140, 100, 80, 60):
        short = cite[:n].rsplit(" ", 1)[0]
        if len(short) >= 24 and citation_in_source(short, body):
            return short
    return None


def slice_exactly_at_sentence(
    fragment: str,
    sentence: str,
    *,
    lookback: int = 3,
    max_following: int = 10,
) -> dict | None:
    """
    Corta garantizando que `sentence` (o su literal resuelto) sea CURRENT.
    """
    body = _strip_progress_header_if_any(fragment)
    if not body or not (sentence or "").strip():
        return None
    matched = resolve_literal_guide_sentence(body, sentence) or sentence.strip()
    matched = re.sub(r"\.{2,}", ".", matched).strip()
    sentences = _guide_sentences(body)
    if not sentences:
        return None

    cur_i = -1
    m_l = normalize_whitespace(matched).lower()
    for i, s in enumerate(sentences):
        if m_l in s.lower() or s.lower() in m_l:
            cur_i = i
            break
    if cur_i < 0 and len(m_l) >= 24:
        for i, s in enumerate(sentences):
            if m_l[:24] in s.lower():
                cur_i = i
                break
    if cur_i < 0:
        # Insertar el literal como current y tomar following del cuerpo tras el índice
        idx = find_anchor_in_text(body, matched)
        if idx < 0:
            return None
        before = body[:idx]
        after = body[idx + len(matched) :]
        prev_sents = _guide_sentences(before)[-lookback:]
        follow_sents = _guide_sentences(matched + " " + after)
        # quitar el current si quedó primero
        if follow_sents and (
            normalize_whitespace(follow_sents[0]).lower() in m_l
            or m_l in normalize_whitespace(follow_sents[0]).lower()
        ):
            follow_sents = follow_sents[1:]
        following = follow_sents[:max_following]
        return {
            "previous": " ".join(prev_sents),
            "current": matched,
            "following": following,
            "following_text": " ".join(following),
            "cite": matched,
            "source_fragment": body,
        }

    prev_sents = sentences[max(0, cur_i - lookback) : cur_i]
    current = matched  # forzar el literal de la guía
    following = sentences[cur_i + 1 : cur_i + 1 + max_following]
    return {
        "previous": " ".join(prev_sents),
        "current": current,
        "following": following,
        "following_text": re.sub(r"\.\s*\.", ".", " ".join(following)).strip(),
        "cite": current,
        "source_fragment": body,
    }


def slice_around_anchor(
    fragment: str,
    anchor: str,
    *,
    max_following: int = 10,
) -> dict | None:
    """
    Corta texto literal de la guía alrededor del ancla.
    Devuelve {previous, current, following: list[str], following_text, cite}.
    following ≈ las próximas max_following oraciones (prosa, sin numerar).
    """
    body = _strip_progress_header_if_any(fragment)
    if not body or not (anchor or "").strip():
        return None
    if not citation_in_source(anchor, body) and find_anchor_in_text(body, anchor) < 0:
        short = normalize_whitespace(anchor)
        if len(short) > 40:
            short = short[:80]
        if find_anchor_in_text(body, short) < 0 and not citation_in_source(short, body):
            return None
        anchor = short

    sentences = _guide_sentences(body)
    anc_l = normalize_whitespace(anchor).lower()
    # Limpiar ancla igual que oraciones (por si traía ====)
    anc_clean = _clean_guide_sentence(anchor) or normalize_whitespace(anchor)
    anc_l = anc_clean.lower()

    cur_i = -1
    for i, s in enumerate(sentences):
        if anc_l in s.lower() or s.lower() in anc_l:
            cur_i = i
            break
    if cur_i < 0 and len(anc_l) >= 20:
        for i, s in enumerate(sentences):
            if anc_l[:20] in s.lower():
                cur_i = i
                break

    if cur_i >= 0 and sentences:
        lookback = min(3, cur_i)
        prev_sents = sentences[cur_i - lookback : cur_i] if lookback else []
        previous = " ".join(prev_sents)
        current = sentences[cur_i]
        following = sentences[cur_i + 1 : cur_i + 1 + max_following]
        cite = anc_clean.strip() if citation_in_source(anc_clean, body) else current[:200]
        following_text = re.sub(r"\.\s*\.", ".", " ".join(following)).strip()
        return {
            "previous": previous,
            "current": current,
            "following": following,
            "following_text": following_text,
            "cite": cite,
            "source_fragment": body,
        }

    paras = _split_paragraphs(body)
    if not paras:
        return None

    cur_i = 0
    for i, p in enumerate(paras):
        if anc_l in p.lower() or p.lower() in anc_l:
            cur_i = i
            break
    else:
        for i, p in enumerate(paras):
            if len(anc_l) >= 20 and anc_l[:20] in p.lower():
                cur_i = i
                break

    previous = " ".join(paras[max(0, cur_i - 2) : cur_i]) if cur_i > 0 else ""
    current = paras[cur_i]
    following = paras[cur_i + 1 : cur_i + 1 + max_following]
    cite = (anc_clean or anchor).strip()
    if not citation_in_source(cite, body):
        cite = current[:200]
    return {
        "previous": previous,
        "current": current,
        "following": following,
        "following_text": " ".join(following),
        "cite": cite,
        "source_fragment": body,
    }


def _strip_progress_header_if_any(fragment: str) -> str:
    if "---" in (fragment or ""):
        return fragment.split("---", 1)[-1].strip()
    return (fragment or "").strip()
