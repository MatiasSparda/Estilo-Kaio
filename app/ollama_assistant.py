import re

import customtkinter as ctk

from .gemma_translate import gemma_generate, is_server_running, REASONING_SEARCH
from .guide_parser import (
    citation_in_source,
    extract_felipe_line,
    extract_fuente_line,
    find_anchor_in_text,
    locate_anchor_by_terms,
    resolve_literal_guide_sentence,
    slice_around_anchor,
    slice_exactly_at_sentence,
    strip_fuente_from_steps,
)
from .proper_nouns import apply_proper_noun_format, polish_spanish_guide
from . import ui_theme as theme

ASSISTANT_LANGUAGES = {
    "es": "español",
    "en": "English",
    "pt": "português",
    "fr": "français",
    "de": "Deutsch",
    "it": "italiano",
    "ja": "日本語",
    "ko": "한국어",
    "zh": "中文",
}

NOT_FOUND_MESSAGES = {
    "es": "No encontré información sobre esto en la guía.",
    "en": "I couldn't find information about this in the guide.",
    "pt": "Não encontrei informações sobre isso no guia.",
    "fr": "Je n'ai trouvé aucune information à ce sujet dans le guide.",
    "de": "Dazu habe ich in der Anleitung keine Informationen gefunden.",
    "it": "Non ho trovato informazioni su questo nella guida.",
    "ja": "ガイドにこの情報は見つかりませんでした。",
    "ko": "가이드에서 이 정보를 찾을 수 없습니다.",
    "zh": "指南中未找到相关信息。",
}

SECTION_PICK_PROMPT = """You pick ONE guide walkthrough section for a player question.
The guide titles may be in a different language than the question. That is OK.
Reply with ONLY a section number from the list, or the word none.
No other text.

NEVER pick Introduction, Contents, Index, Credits, Bosses list, FAQ, or version notes.
Prefer concrete walkthrough / area / dungeon / quest sections.

If the player finished something and asks what next, pick the section covering what comes AFTER.

TITLES:
{titles}

PLAYER MESSAGE:
{query_text}
"""

LOCATE_PROMPT = """You locate where the player is inside a guide excerpt.
The player message may be in another language. Match by meaning.
They say what they JUST FINISHED. Copy 1-2 sentences VERBATIM from the EXCERPT
that come RIGHT AFTER that finished event (reward / leaving / next objective).

CRITICAL:
- Copy ONLY words that appear in EXCERPT.
- Do NOT rewrite the player message.
- Do NOT use first person ("I finished...").

Reply with ONLY one line:
ANCLA: <exact quote from excerpt>

Example:
EXCERPT: ... After you win the dance, he gives you the Brother Emblem. Next, go play Target Carts...
PLAYER: acabo de superar el baile goron
ANCLA: After you win the dance, he gives you the Brother Emblem.

EXCERPT:
{guide_text}

PLAYER MESSAGE:
{query_text}
"""

TRANSLATE_PLAIN_PROMPT = """Translate this game-guide excerpt into natural {response_language}.
Rules:
- Output ONLY the translation. No labels, no notes, no English left except proper names.
- Proper names / items: English + (Spanish gloss).
  Examples: Tune of Currents (Melodía de las Corrientes), Brother Emblem (Emblema Hermano).
- "Play" a Tune/Song/Melody = "Toca", NEVER "Juega".
  Correct: Toca Tune of Currents (Melodía de las Corrientes) para volver al presente.
  Wrong: Play the Tune of Currents (...); Juega la melodía...
- vine / vine-covered = enredadera (NEVER "vino"/wine).
- Use correct Spanish grammar (a la cueva, e inundar, unas cuantas, el área).
- Do not invent places, items, or NPCs.

TEXT:
{text}
"""

TRANSLATE_PROMPT = """You translate game-guide excerpts into natural {response_language}.
You may ONLY use facts from the excerpts. Do not invent places, items, or NPCs.

Style rules:
- Sound like a clear walkthrough in {response_language}, not a word-for-word calque.
- The whole sentence must be in {response_language}. Do NOT leave English verbs (Play, Go, Climb, Push…).
- Proper nouns / item names: keep the English name and add a short Spanish gloss in parentheses.
  Examples: Brother Emblem (Emblema Hermano), Pegasus Seeds (Semillas Pegaso),
  Switch Hook (Gancho Cambiador), Tune of Currents (Melodía de las Corrientes).
- Verb "Play" with a Tune/Song/Melody/Instrument = "Toca" or "Reproduce", NEVER "Juega".
  Example: Play the Tune of Currents → Toca Tune of Currents (Melodía de las Corrientes)
- vine / vine-covered = enredadera (NEVER translate as "vino").
- Do NOT number steps.
- Do NOT copy labels like PREVIOUS, CURRENT, FOLLOWING, GUIDE_*, NOTA into the answer.
- ACTUAL must translate ONLY the GUIDE_NOW excerpt (do not mix in other excerpts).

Output exactly this structure (and nothing else):

ANTERIOR:
<translation of GUIDE_BEFORE, or — if empty>

ACTUAL:
<translation of GUIDE_NOW only>

SIGUIENTES:
<translation of GUIDE_NEXT only; continuous prose>

FUENTE: <one short literal English quote from the excerpts>

FELIPE: <one short Chilean slang quip about the tip; no new mechanics>

GUIDE_BEFORE:
{previous}

GUIDE_NOW:
{current}

GUIDE_NEXT:
{following}
"""

SYSTEM_PROMPT_TEMPLATE = """Eres un asistente de walkthrough. Solo usá el FRAGMENTO DE GUÍA.

FRAGMENTO DE GUÍA:
{guide_text}

PREGUNTA:
{query_text}

REGLAS:
- Respondé en {response_language} traduciendo/clarificando SOLO el fragmento.
- No inventes NPCs, lugares ni objetos ausentes del fragmento.
- Nombres propios: inglés + (traducción).
- Si no alcanza, exactamente: {not_found_msg}
- Si hay tip útil, terminá con estas dos líneas (en este orden):
  FUENTE: frase literal del fragmento
  FELIPE: una sola frase corta en jerga chilena (weón/bacán) comentando el tip, sin inventar mecánicas ni spoilers nuevos
"""

FELIPE_PROMPT = """Sos Felipe, weón bacán de Chile. Leé el tip de guía y comentá en UNA frase corta con jerga chilena.
Reglas:
- Solo comentar lo que ya dice el tip. No inventes mecánicas, lugares ni spoilers.
- Una sola línea. Sin comillas. Sin prefijo.
- Tono amigo gamer (cachai, bacán, weón, filete, la raja…).

TIP:
{tip_text}

Respondé solo la frase:
"""

_PROGRESS_RE = re.compile(
    r"(?:"
    r"super[eéoó]|termin[eéoó]|acab[oó]|completé|complet[eéoó]|pas[eéoó]|"
    r"finished|beat|cleared|defeated|done with|"
    r"no\s+s[eé]\s+qu[eé]\s+hacer|qu[eé]\s+hago|ahora\s+qu[eé]|"
    r"what\s+next|where\s+(?:do\s+i\s+)?go|stuck"
    r")",
    re.IGNORECASE,
)


def is_progress_query(query_text: str) -> bool:
    return bool(_PROGRESS_RE.search(query_text or ""))


def normalize_like(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def extract_ancla_line(response: str) -> str | None:
    if not response:
        return None
    for line in response.splitlines():
        m = re.match(r"^\s*ANCLA\s*:\s*(.+)$", line.strip(), flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().strip('"').strip("'").strip("<>").strip()
    m = re.search(r"ANCLA\s*:\s*(.+)", response, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip().split("\n")[0].strip().strip('"').strip("'")
    return None


def _split_sentences_es(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", (text or "").strip())
    return [p.strip() for p in parts if p and p.strip()]


def _paragraphize_every_n(text: str, n: int = 2) -> str:
    """Agrupa oraciones de a N con punto y aparte."""
    sents = _split_sentences_es(text)
    if len(sents) <= 1:
        return (text or "").strip()
    chunks = []
    for i in range(0, len(sents), n):
        chunks.append(" ".join(sents[i : i + n]))
    return "\n\n".join(chunks)


def _format_section_body(label_key: str, body: str) -> str:
    body = (body or "").strip()
    if not body or body == "—":
        return "—"
    if label_key == "SIGUIENTES":
        return _paragraphize_every_n(body, 2)
    if label_key == "ANTERIOR":
        return _paragraphize_every_n(body, 2)
    return body


def _rewrite_sections_spacing(steps: str) -> str:
    """Aplica punto y aparte cada 2 oraciones en Antes / Qué sigue."""
    if not steps:
        return steps
    markers = ["ANTERIOR:", "ACTUAL:", "SIGUIENTES:"]
    upper = steps.upper()
    positions = []
    for key in markers:
        idx = upper.find(key)
        if idx >= 0:
            positions.append((idx, key))
    if not positions:
        return steps
    positions.sort()
    parts = []
    head = steps[: positions[0][0]]
    if head.strip():
        parts.append(head.rstrip())
    for i, (idx, key) in enumerate(positions):
        start = idx + len(key)
        end = positions[i + 1][0] if i + 1 < len(positions) else len(steps)
        raw_body = steps[start:end]
        # no comer FUENTE si quedó pegada a SIGUIENTES
        raw_body = re.sub(r"\n?FUENTE\s*:.*$", "", raw_body, flags=re.I | re.S).strip()
        body = _format_section_body(key.rstrip(":"), raw_body)
        parts.append(f"{key}\n{body}")
    return "\n\n".join(parts)


def _sanitize_translation_leaks(steps: str) -> str:
    """Saca etiquetas del prompt / notas del modelo que se cuelan en la respuesta."""
    if not steps:
        return steps
    text = steps
    text = re.sub(
        r"(?im)^\s*(PREVIOUS|CURRENT|FOLLOWING|GUIDE_BEFORE|GUIDE_NOW|GUIDE_NEXT)\s*:.*$",
        "",
        text,
    )
    text = re.sub(
        r"(?i)\b(PREVIOUS|CURRENT|FOLLOWING|GUIDE_BEFORE|GUIDE_NOW|GUIDE_NEXT)\s*:",
        "",
        text,
    )
    text = re.sub(r"(?im)^\s*NOTA\s*:.*$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _replace_section_body(steps: str, section_key: str, new_body: str) -> str:
    """Reemplaza el cuerpo de ANTERIOR/ACTUAL/SIGUIENTES."""
    key = section_key.upper().rstrip(":") + ":"
    m = re.search(
        rf"({re.escape(key)}\s*)(.*?)(?=\n\s*(?:ANTERIOR|ACTUAL|SIGUIENTES|FUENTE)\s*:|$)",
        steps or "",
        flags=re.I | re.S,
    )
    if not m:
        return f"{key}\n{new_body}\n\n{steps or ''}".strip()
    return (steps or "")[: m.start(2)] + new_body.strip() + "\n" + (steps or "")[m.end(2) :]


def _denumber_siguientes(steps: str) -> str:
    """Si el modelo numeró SIGUIENTES, lo aplana a prosa continua."""
    if not steps or "SIGUIENTES:" not in steps.upper():
        return steps
    m = re.search(
        r"(SIGUIENTES:\s*)(.*?)(?=\n\s*FUENTE:|$)",
        steps,
        flags=re.I | re.S,
    )
    if not m:
        return steps
    body = m.group(2).strip()
    if not re.search(r"^\s*\d+[\).\]]\s+", body, re.M):
        return steps
    lines = []
    for line in body.splitlines():
        line = re.sub(r"^\s*\d+[\).\]]\s*", "", line).strip()
        if line:
            lines.append(line)
    prose = " ".join(lines)
    return steps[: m.start(2)] + prose + steps[m.end(2) :]


def _format_following_for_prompt(blocks: list[str]) -> str:
    if not blocks:
        return "(none)"
    return " ".join(b.strip() for b in blocks if b and b.strip())


def _fallback_display_from_slice(sl: dict, response_language: str) -> str:
    _ = response_language
    following = sl.get("following") or []
    if isinstance(following, str):
        following_text = following
    else:
        following_text = " ".join(b.strip() for b in following if b and b.strip())
    previous = sl.get("previous") or "—"
    return _rewrite_sections_spacing(
        "\n".join(
            [
                "ANTERIOR:",
                previous,
                "",
                "ACTUAL:",
                sl.get("current") or "—",
                "",
                "SIGUIENTES:",
                following_text or "—",
            ]
        )
    )


def last_continue_sentence(steps_text: str) -> str | None:
    """Última oración útil de 'Qué sigue' (o de toda la respuesta)."""
    sections = AssistantResponseWindow._split_sections(steps_text or "")
    pool = ""
    for title, content in sections:
        if title == "Qué sigue":
            pool = content or ""
            break
    if not pool.strip():
        pool = steps_text or ""
        pool = re.sub(
            r"(?i)\b(ANTERIOR|ACTUAL|SIGUIENTES|FUENTE)\s*:",
            " ",
            pool,
        )
    flat = re.sub(r"\s+", " ", (pool or "").replace("\n", " ")).strip()
    sents = _split_sentences_es(flat)
    sents = [
        s.strip()
        for s in sents
        if s and s.strip() not in {"—", "-"} and len(s.strip()) >= 20
    ]
    return sents[-1] if sents else None


class AssistantResponseWindow(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        query_text,
        steps_text,
        source_text=None,
        on_continue=None,
        continue_source=None,
        felipe_text=None,
    ):
        super().__init__(parent)

        self._parent_app = parent
        self._steps_text = steps_text or ""
        self._on_continue = on_continue
        self._continue_source = (continue_source or "").strip() or None
        self._continue_display = last_continue_sentence(self._steps_text)

        self.title("Respuesta del asistente")
        self.minsize(640, 560)
        self.attributes("-topmost", True)
        self.configure(fg_color=theme.BG)

        # Restaurar geometría guardada
        saved = None
        if hasattr(parent, "response_geometry"):
            saved = parent.response_geometry
        if saved:
            try:
                self.geometry(saved)
            except Exception:
                self.geometry("780x720")
        else:
            self.geometry("780x720")

        header = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(
            header,
            text="Asistente de guía",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=theme.PRIMARY,
        ).pack(anchor="w", padx=theme.PAD_LG, pady=theme.PAD)

        body = ctk.CTkScrollableFrame(self, fg_color=theme.BG)
        body.pack(fill="both", expand=True, padx=theme.PAD, pady=theme.PAD_SM)

        self._block(body, "Tu consulta", query_text, height=52)
        sections = self._split_sections(steps_text)
        if sections:
            for title, content in sections:
                # Más alto en “Qué sigue”
                base = 40 + content.count("\n") * 22 + len(content) // 6
                if title == "Qué sigue":
                    h = max(180, min(420, base))
                elif title == "Antes":
                    h = max(90, min(180, base))
                elif title == "Estás acá":
                    h = max(88, min(200, base + 24))
                else:
                    h = max(64, min(140, base))
                self._block(body, title, content, height=h)
        else:
            self._block(body, "Respuesta", steps_text, height=240)

        if source_text:
            self._block(body, "Fuente (guía)", source_text, height=64)

        if felipe_text and str(felipe_text).strip():
            self._block(body, "Felipe dice:", str(felipe_text).strip(), height=72)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=(theme.PAD_SM, theme.PAD))

        ctk.CTkButton(
            btns,
            text="Cerrar",
            command=self._on_close,
            fg_color=theme.SECONDARY,
            hover_color=theme.SECONDARY_HOVER,
            height=36,
            width=120,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btns,
            text="Continuar",
            command=self._continue,
            fg_color=theme.PRIMARY,
            hover_color=theme.PRIMARY_HOVER,
            height=36,
            width=140,
        ).pack(side="left")

        self.bind("<Escape>", lambda e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._on_configure)
        self.focus_force()

    def _on_configure(self, event=None):
        if event and event.widget is not self:
            return
        try:
            geo = self.geometry()
            if hasattr(self._parent_app, "response_geometry"):
                self._parent_app.response_geometry = geo
        except Exception:
            pass

    def _on_close(self):
        try:
            if hasattr(self._parent_app, "response_geometry"):
                self._parent_app.response_geometry = self.geometry()
            if hasattr(self._parent_app, "save_config"):
                self._parent_app.save_config()
        except Exception:
            pass
        self.destroy()

    def _continue(self):
        # Preferir oración fuente (idioma de la guía); fallback a la traducida
        source = self._continue_source
        display = self._continue_display or source
        if display:
            display = polish_spanish_guide(display, source or "")
        if not source and not display:
            from tkinter import messagebox

            messagebox.showwarning(
                "Continuar",
                "No encontré una última oración para seguir.",
                parent=self,
            )
            return
        cb = self._on_continue
        try:
            if hasattr(self._parent_app, "response_geometry"):
                self._parent_app.response_geometry = self.geometry()
            if hasattr(self._parent_app, "save_config"):
                self._parent_app.save_config()
        except Exception:
            pass
        self.destroy()
        if cb:
            cb(source or display, display or source)

    def _block(self, parent, title, text, height=80):
        card = ctk.CTkFrame(parent, fg_color=theme.SURFACE, corner_radius=8)
        card.pack(fill="x", pady=(0, theme.PAD_SM))
        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=theme.PRIMARY,
        ).pack(anchor="w", padx=theme.PAD, pady=(theme.PAD_SM, 4))
        box = ctk.CTkTextbox(
            card,
            height=height,
            font=ctk.CTkFont(size=13),
            fg_color=theme.SURFACE_2,
            text_color=theme.TEXT,
            wrap="word",
        )
        box.pack(fill="x", padx=theme.PAD, pady=(0, theme.PAD_SM))
        box.insert("1.0", text or "")
        box.configure(state="disabled")

    @staticmethod
    def _split_sections(steps_text: str) -> list[tuple[str, str]]:
        text = steps_text or ""
        markers = [
            ("ANTERIOR:", "Antes"),
            ("ACTUAL:", "Estás acá"),
            ("SIGUIENTES:", "Qué sigue"),
        ]
        upper = text.upper()
        if "ANTERIOR:" not in upper and "ACTUAL:" not in upper:
            return []
        positions = []
        for key, label in markers:
            idx = upper.find(key)
            if idx >= 0:
                positions.append((idx, key, label))
        if not positions:
            return []
        positions.sort()
        out = []
        for i, (idx, key, label) in enumerate(positions):
            start = idx + len(key)
            end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
            content = text[start:end].strip()
            content = re.sub(r"\n?FUENTE\s*:.*$", "", content, flags=re.IGNORECASE).strip()
            if label in ("Qué sigue", "Antes"):
                content = _paragraphize_every_n(content, 2)
            if content:
                out.append((label, content))
        return out


class GuideAssistant:
    """Asistente de guía vía Gemma/LiteRT (offline)."""

    def check_gemma_connection(self) -> bool:
        return is_server_running()

    def check_ollama_connection(self) -> bool:
        """Compat: antes Ollama, ahora Gemma."""
        return self.check_gemma_connection()

    def _generate(
        self,
        prompt: str,
        temperature: float = 0.2,
        num_predict: int = 160,
        timeout: int = 45,
        reasoning_effort: str | None = None,
    ):
        raw, err = gemma_generate(
            prompt,
            temperature=temperature,
            max_tokens=num_predict,
            timeout=float(timeout),
            reasoning_effort=reasoning_effort,
        )
        return raw, err

    def pick_section_index(self, titles: list[str], query_text: str) -> int | None:
        if not titles:
            return None
        lines = "\n".join(f"{i}. {t}" for i, t in enumerate(titles, start=1))
        prompt = SECTION_PICK_PROMPT.replace("{titles}", lines).replace(
            "{query_text}", query_text or ""
        )
        raw, err = self._generate(
            prompt,
            temperature=0.0,
            num_predict=20,
            timeout=30,
            reasoning_effort=REASONING_SEARCH,
        )
        if err or not raw:
            return None
        cleaned = raw.strip().lower()
        if "none" in cleaned and not re.search(r"\d", cleaned):
            return None
        match = re.search(r"\b(\d{1,3})\b", cleaned)
        if not match:
            return None
        idx = int(match.group(1))
        if 1 <= idx <= len(titles):
            return idx
        return None

    def locate_anchor(self, guide_text: str, query_text: str) -> str | None:
        # Primero ancla determinista (el LLM suele parafrasear al jugador)
        by_terms = locate_anchor_by_terms(guide_text or "", query_text or "")

        prompt = LOCATE_PROMPT.replace("{guide_text}", (guide_text or "")[:9000]).replace(
            "{query_text}", query_text or ""
        )
        raw, err = self._generate(prompt, temperature=0.0, num_predict=80, timeout=40)
        ancla = extract_ancla_line(raw) if not err else None
        if ancla and self._ancla_usable(ancla, guide_text or "", query_text or ""):
            return ancla
        raw2, err2 = self._generate(
            prompt + "\n\nWRONG if you invent. Copy a sentence that EXISTS in EXCERPT only.\nANCLA:",
            temperature=0.0,
            num_predict=80,
            timeout=40,
        )
        ancla2 = extract_ancla_line(raw2) if not err2 else None
        if ancla2 and self._ancla_usable(ancla2, guide_text or "", query_text or ""):
            return ancla2
        return by_terms

    @staticmethod
    def _ancla_usable(ancla: str, guide_text: str, query_text: str) -> bool:
        if not ancla or len(ancla.strip()) < 20:
            return False
        if not citation_in_source(ancla, guide_text):
            return False
        # Rechazar parafraseo de la pregunta del jugador
        if re.search(
            r"\b(i just|i finished|i don't|i beat|acabo de|no s[eé] qu[eé])\b",
            ancla,
            re.I,
        ):
            return False
        qn = normalize_like(query_text)
        an = normalize_like(ancla)
        if qn and an and (an in qn or qn in an):
            return False
        return True

    def _repair_actual_if_drifted(self, steps: str, sl: dict, response_language: str) -> str:
        """Si ACTUAL se fue de tema (mucho más largo que CURRENT), retraducir solo CURRENT."""
        cur_src = (sl.get("current") or "").strip()
        if not cur_src:
            return steps
        m = re.search(
            r"ACTUAL:\s*(.*?)(?=\n\s*SIGUIENTES:|\n\s*FUENTE:|$)",
            steps or "",
            flags=re.I | re.S,
        )
        if not m:
            return steps
        act = m.group(1).strip()
        # CURRENT corto y ACTUAL inflado → el modelo mezcló bloques
        if len(cur_src) <= 160 and len(act) > max(220, len(cur_src) * 2):
            lang_name = ASSISTANT_LANGUAGES.get(response_language, ASSISTANT_LANGUAGES["es"])
            prompt = (
                f"Translate into natural {lang_name}. "
                "Proper nouns: English + (Spanish), e.g. Brother Emblem (Emblema Hermano).\n"
                "Return ONLY the translation.\n\n"
                f"{cur_src}"
            )
            raw, err = self._generate(prompt, temperature=0.2, num_predict=120, timeout=35)
            if not err and (raw or "").strip():
                filled = raw.strip().split("\n")[0].strip()
                return (steps or "")[: m.start(1)] + filled + "\n" + (steps or "")[m.end(1) :]
        return steps

    def _repair_anterior_if_empty(self, steps: str, sl: dict, response_language: str) -> str:
        """Si ANTERIOR quedó vacío/— pero hay oraciones previas, traducirlas aparte."""
        prev_src = (sl.get("previous") or "").strip()
        if not prev_src:
            return steps
        m = re.search(
            r"ANTERIOR:\s*(.*?)(?=\n\s*ACTUAL:|\n\s*SIGUIENTES:|$)",
            steps or "",
            flags=re.I | re.S,
        )
        body = (m.group(1).strip() if m else "")
        src_sents = len(_split_sentences_es(prev_src))
        out_sents = len(_split_sentences_es(body)) if body not in {"", "—", "-"} else 0
        # Reparar si falta casi todo el bloque anterior
        if out_sents >= max(1, src_sents - 1) and body not in {"", "—", "-"}:
            return steps

        lang_name = ASSISTANT_LANGUAGES.get(response_language, ASSISTANT_LANGUAGES["es"])
        prompt = (
            f"Translate these guide sentences into natural {lang_name}.\n"
            "Proper nouns: English name + (Spanish gloss), e.g. Brother Emblem (Emblema Hermano).\n"
            "Return ONLY the translation, no labels.\n\n"
            f"{prev_src}"
        )
        raw, err = self._generate(prompt, temperature=0.2, num_predict=220, timeout=45)
        if err or not (raw or "").strip():
            filled = _paragraphize_every_n(prev_src, 2)
        else:
            filled = _paragraphize_every_n(raw.strip(), 2)
        if not m:
            return f"ANTERIOR:\n{filled}\n\n{steps}"
        return (steps or "")[: m.start(1)] + filled + (steps or "")[m.end(1) :]

    def _translate_plain(self, text: str, response_language: str, num_predict: int = 280) -> str:
        """Traduce un bloque suelto (sin mezclar secciones)."""
        src = (text or "").strip()
        if not src or src in {"(empty)", "(none)", "—", "-"}:
            return "—"
        lang_name = ASSISTANT_LANGUAGES.get(response_language, ASSISTANT_LANGUAGES["es"])
        prompt = TRANSLATE_PLAIN_PROMPT.replace("{response_language}", lang_name).replace(
            "{text}", src
        )
        # Más tokens si el bloque es largo (Qué sigue)
        predict = max(num_predict, min(900, 40 + len(src) // 2))
        raw, err = self._generate(prompt, temperature=0.15, num_predict=predict, timeout=75)
        if err or not (raw or "").strip():
            return src
        filled = raw.strip()
        filled = re.sub(
            r"(?i)^(ANTERIOR|ACTUAL|SIGUIENTES|TRANSLATION|FUENTE)\s*:\s*",
            "",
            filled,
        ).strip()
        # Si el modelo devolvió estructura, quedarse con el cuerpo útil
        filled = re.sub(r"(?is)\n\s*FUENTE\s*:.*$", "", filled).strip()
        filled = apply_proper_noun_format(src, filled)
        filled = polish_spanish_guide(filled, src)
        return filled or src

    def _translation_looks_bad(self, spanish: str, english: str) -> bool:
        """Heurística: inglés residual o calcos conocidos."""
        es = spanish or ""
        en = english or ""
        if not es or es == "—":
            return bool(en.strip())
        if re.search(r"\b(Play|Climb|Push|Go down|Go up|Outside,)\b", es):
            return True
        if re.search(r"\bvines?\b", en, flags=re.I) and re.search(r"\bde vino\b", es, flags=re.I):
            return True
        if re.search(r"\bJuega\b", es) and re.search(r"\btune|song|melody\b", en, flags=re.I):
            return True
        if re.search(r"\bMelod[ií]a de Echoes\b", es, flags=re.I):
            return True
        if re.search(r"\bal cueva\b", es, flags=re.I):
            return True
        return False

    def translate_slice(self, sl: dict, response_language: str = "es") -> dict:
        not_found = NOT_FOUND_MESSAGES.get(response_language, NOT_FOUND_MESSAGES["es"])

        prev_src = (sl.get("previous") or "").strip()
        cur_src = (sl.get("current") or "").strip()
        foll_src = (sl.get("following_text") or "").strip()
        if not foll_src:
            foll_src = _format_following_for_prompt(sl.get("following") or [])
            if foll_src in {"(none)", ""}:
                foll_src = ""

        # Traducción por sección: evita que el modelo mezcle bloques / deje inglés
        prev_es = self._translate_plain(prev_src, response_language, num_predict=220) if prev_src else "—"
        cur_es = self._translate_plain(cur_src, response_language, num_predict=160) if cur_src else "—"
        foll_es = self._translate_plain(foll_src, response_language, num_predict=700) if foll_src else "—"

        # Reintento si quedó basura típica
        if prev_src and self._translation_looks_bad(prev_es, prev_src):
            prev_es = self._translate_plain(prev_src, response_language, num_predict=260)
        if cur_src and self._translation_looks_bad(cur_es, cur_src):
            cur_es = self._translate_plain(cur_src, response_language, num_predict=180)
        if foll_src and self._translation_looks_bad(foll_es, foll_src):
            foll_es = self._translate_plain(foll_src, response_language, num_predict=800)

        steps = _rewrite_sections_spacing(
            "\n".join(
                [
                    "ANTERIOR:",
                    prev_es or "—",
                    "",
                    "ACTUAL:",
                    cur_es or "—",
                    "",
                    "SIGUIENTES:",
                    foll_es or "—",
                ]
            )
        )
        steps = _sanitize_translation_leaks(steps)
        steps = self._apply_proper_nouns_to_steps(steps, sl)
        steps = _rewrite_sections_spacing(steps)

        cite = sl.get("cite") or cur_src
        joined_src = "\n".join(
            [
                prev_src,
                cur_src,
                *list(sl.get("following") or []),
            ]
        )
        if cite and not citation_in_source(cite, joined_src):
            cite = cur_src or cite

        if not steps or normalize_like(not_found) in normalize_like(steps):
            steps = _fallback_display_from_slice(sl, response_language)

        following = list(sl.get("following") or [])
        continue_anchor = None
        if following:
            continue_anchor = resolve_literal_guide_sentence(
                sl.get("source_fragment") or "\n".join(following),
                following[-1],
            ) or re.sub(r"\.{2,}", ".", following[-1].strip())
        if not continue_anchor:
            cur = (sl.get("current") or "").strip()
            if cur:
                continue_anchor = resolve_literal_guide_sentence(
                    sl.get("source_fragment") or cur, cur
                ) or re.sub(r"\.{2,}", ".", cur)

        return {
            "ok": True,
            "steps": steps,
            "source": cite,
            "continue_anchor": continue_anchor,
            "felipe": self._generate_felipe(steps, response_language),
            "error": None,
            "raw": None,
        }

    def _generate_felipe(self, tip_text: str, response_language: str = "es") -> str | None:
        """Comentario chileno corto sobre el tip. None si falla o tip vacío."""
        tip = (tip_text or "").strip()
        if not tip or tip == "—":
            return None
        # Solo español chilensis tiene sentido para Felipe
        if (response_language or "es").lower() not in ("es", "español", "spanish"):
            return None
        prompt = FELIPE_PROMPT.replace("{tip_text}", tip[:900])
        raw, err = self._generate(prompt, temperature=0.7, num_predict=60, timeout=25)
        if err or not (raw or "").strip():
            return None
        line = (raw or "").strip().split("\n")[0].strip().strip('"').strip("'")
        line = re.sub(r"^\s*FELIPE\s*:\s*", "", line, flags=re.I).strip()
        if len(line) < 8 or len(line) > 220:
            return None
        return line

    def continue_from_anchor(self, guide_text, source_sentence, response_language="es"):
        """Continuar desde una oración literal de la guía (idioma original)."""
        not_found = NOT_FOUND_MESSAGES.get(response_language, NOT_FOUND_MESSAGES["es"])
        approx = re.sub(r"\.{2,}", ".", (source_sentence or "").strip()).strip()
        body = guide_text or ""
        if not approx or not body:
            return {
                "ok": False,
                "steps": not_found,
                "source": None,
                "continue_anchor": None,
                "felipe": None,
                "error": None,
                "raw": None,
            }

        matched = resolve_literal_guide_sentence(body, approx) or approx
        idx = find_anchor_in_text(body, matched)
        if idx < 0:
            matched2 = resolve_literal_guide_sentence(body, approx)
            if matched2:
                matched = matched2
                idx = find_anchor_in_text(body, matched)
        if idx < 0 and not citation_in_source(matched, body):
            return {
                "ok": False,
                "steps": (
                    "No pude ubicar esa oración literal en la guía para continuar. "
                    "Probá reformular la pregunta."
                ),
                "source": None,
                "continue_anchor": None,
                "felipe": None,
                "error": None,
                "raw": None,
            }
        if idx < 0:
            idx = body.lower().find(matched.lower()[:40]) if len(matched) >= 40 else 0
            if idx < 0:
                idx = 0

        start = max(0, idx - 2500)
        end = min(len(body), idx + max(len(matched), 40) + 12000)
        frag = body[start:end]
        sl = slice_exactly_at_sentence(
            frag, matched, lookback=3, max_following=10
        )
        if not sl or not sl.get("current"):
            return {
                "ok": False,
                "steps": not_found,
                "source": None,
                "continue_anchor": None,
                "felipe": None,
                "error": None,
                "raw": None,
            }
        # Garantía: CURRENT = oración ancla literal
        sl["current"] = matched
        sl["cite"] = matched

        result = self.translate_slice(sl, response_language=response_language)
        # Forzar ACTUAL = traducción fiel del ancla (contexto del jugador)
        result = self._force_actual_to_source(result, matched, response_language)
        return result

    def _apply_proper_nouns_to_steps(self, steps: str, sl: dict) -> str:
        """English (español) en cada sección usando el inglés del slice."""
        if not steps:
            return steps
        src_map = {
            "ANTERIOR": sl.get("previous") or "",
            "ACTUAL": sl.get("current") or "",
            "SIGUIENTES": sl.get("following_text")
            or " ".join(sl.get("following") or []),
        }
        out = steps
        for key, en_src in src_map.items():
            m = re.search(
                rf"({key}:\s*)(.*?)(?=\n\s*(?:ANTERIOR|ACTUAL|SIGUIENTES|FUENTE)\s*:|$)",
                out,
                flags=re.I | re.S,
            )
            if not m:
                continue
            body = m.group(2).strip()
            if not body or body == "—":
                continue
            fixed = apply_proper_noun_format(en_src, body)
            fixed = polish_spanish_guide(fixed, en_src)
            out = out[: m.start(2)] + fixed + "\n" + out[m.end(2) :]
        return out

    def _force_actual_to_source(self, result: dict, source_sentence: str, response_language: str) -> dict:
        """Asegura que ACTUAL sea la traducción completa de la oración ancla."""
        src = (source_sentence or "").strip()
        src = re.sub(r"\.{2,}", ".", src).strip()
        if not src or not result:
            return result
        filled = self._translate_plain(src, response_language, num_predict=160)
        if self._translation_looks_bad(filled, src):
            filled = self._translate_plain(src, response_language, num_predict=180)
        steps = _replace_section_body(result.get("steps") or "", "ACTUAL", filled)
        steps = _sanitize_translation_leaks(steps)
        steps = _rewrite_sections_spacing(steps)
        result = dict(result)
        result["steps"] = steps
        result["source"] = src
        return result

    def query_progress(self, guide_text, query_text, response_language="es"):
        not_found = NOT_FOUND_MESSAGES.get(response_language, NOT_FOUND_MESSAGES["es"])
        fragments = guide_text if isinstance(guide_text, (list, tuple)) else [guide_text]
        fragments = [f for f in fragments if (f or "").strip()]
        if not fragments:
            return {
                "ok": False,
                "steps": not_found,
                "source": None,
                "felipe": None,
                "error": None,
                "raw": None,
            }

        # 1) Ancla rápida por términos en cada ventana (sin LLM)
        # 2) Si ninguna sirve, un solo intento LLM en la primera ventana
        for frag in fragments:
            ancla = locate_anchor_by_terms(frag, query_text or "")
            if not ancla:
                continue
            sl = slice_around_anchor(frag, ancla, max_following=10)
            if sl and sl.get("current"):
                return self.translate_slice(sl, response_language=response_language)

        ancla = self.locate_anchor(fragments[0], query_text or "")
        if ancla:
            sl = slice_around_anchor(fragments[0], ancla, max_following=10)
            if sl and sl.get("current"):
                return self.translate_slice(sl, response_language=response_language)

        return {
            "ok": False,
            "steps": (
                "No pude ubicar ese momento en la guía automáticamente. "
                "Reformulá con un detalle más concreto del lugar o del último evento "
                "(nombre de mazmorra, NPC, objeto)."
            ),
            "source": None,
            "felipe": None,
            "error": None,
            "raw": None,
        }

    def query_guide(self, guide_text, query_text, response_language="es"):
        return self.query_ollama(
            guide_text, query_text, response_language=response_language
        )

    def query_ollama(self, guide_text, query_text, model=None, response_language="es"):
        _ = model
        if is_progress_query(query_text or ""):
            return self.query_progress(guide_text, query_text, response_language)

        lang_name = ASSISTANT_LANGUAGES.get(response_language, ASSISTANT_LANGUAGES["es"])
        not_found = NOT_FOUND_MESSAGES.get(response_language, NOT_FOUND_MESSAGES["es"])
        prompt = (
            SYSTEM_PROMPT_TEMPLATE.replace("{guide_text}", guide_text or "")
            .replace("{query_text}", query_text or "")
            .replace("{response_language}", lang_name)
            .replace("{not_found_msg}", not_found)
        )
        raw, err = self._generate(prompt, temperature=0.15, num_predict=360, timeout=60)
        if err:
            return {
                "ok": False,
                "steps": err,
                "source": None,
                "felipe": None,
                "error": err,
                "raw": None,
            }

        cite = extract_fuente_line(raw or "")
        felipe = extract_felipe_line(raw or "")
        steps = strip_fuente_from_steps(raw or "")
        if cite and not citation_in_source(cite, guide_text or ""):
            cite = None
        if not cite or not steps or normalize_like(not_found) in normalize_like(raw or ""):
            return {
                "ok": False,
                "steps": not_found,
                "source": None,
                "felipe": None,
                "error": None,
                "raw": raw,
            }
        if not felipe:
            felipe = self._generate_felipe(steps, response_language)
        return {
            "ok": True,
            "steps": steps,
            "source": cite,
            "felipe": felipe,
            "error": None,
            "raw": raw,
        }


# Compat imports viejos
OllamaAssistant = GuideAssistant
