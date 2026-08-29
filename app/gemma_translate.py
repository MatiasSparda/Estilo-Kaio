"""IA offline unificada: LiteRT-LM + Gemma 4 E4B (traducción + guía)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable

import requests

LITERT_HOST = "127.0.0.1"
LITERT_PORT = 9379
LITERT_BASE = f"http://{LITERT_HOST}:{LITERT_PORT}"

DEFAULT_MODEL = "gemma4-e4b"
LEGACY_MODELS = ("gemma4-e2b",)

# LiteRT default = high; traducción usa medium en ambas pasadas.
REASONING_TRANSLATE = "medium"
REASONING_REVIEW = "high"
REASONING_SEARCH = "fast"

MODEL_PRESETS: dict[str, dict[str, str]] = {
    "gemma4-e4b": {
        "hf_repo": "litert-community/gemma-4-E4B-it-litert-lm",
        "file": "gemma-4-E4B-it.litertlm",
        "label": "Gemma 4 E4B (~3.7 GB)",
        "size_hint": "~3.7 GB",
    },
}

BACKEND_LABELS = {
    "cpu": "RAM (CPU)",
    "gpu": "VRAM (GPU)",
}

_preferred_backend: str = "cpu"

LANG_NAMES = {
    "en": "English",
    "es": "Spanish",
    "ja": "Japanese",
    "ko": "Korean",
    "zh-CN": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
    "pt": "Portuguese",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "ru": "Russian",
    "ar": "Arabic",
}


def find_litert_lm() -> str | None:
    return shutil.which("litert-lm") or shutil.which("litert-lm.exe")


def litert_config_path() -> Path:
    return Path.home() / ".litert-lm" / "estilo-kaio.json"


def set_preferred_backend(mode: str | None) -> None:
    global _preferred_backend
    m = (mode or "cpu").strip().lower()
    _preferred_backend = m if m in BACKEND_LABELS else "cpu"


def get_preferred_backend() -> str:
    return _preferred_backend if _preferred_backend in BACKEND_LABELS else "cpu"


def write_litert_config(
    backend: str | None = None,
    model_id: str | None = None,
) -> Path:
    """Escribe config LiteRT (backend cpu/gpu) para litert-lm serve."""
    b = (backend or get_preferred_backend()).lower()
    if b not in BACKEND_LABELS:
        b = "cpu"
    mid = model_id or DEFAULT_MODEL
    path = litert_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    threads = max(4, min(16, (os.cpu_count() or 8)))
    cfg = {
        "default": {
            "backend": b,
            "cpu_thread_count": threads,
            "max_num_tokens": 8192,
        },
        "models": {
            mid: {"backend": b},
        },
    }
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    set_preferred_backend(b)
    return path


def is_server_running(timeout: float = 1.5) -> bool:
    try:
        r = requests.get(f"{LITERT_BASE}/v1/models", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def list_models(timeout: float = 3.0) -> list[str]:
    try:
        r = requests.get(f"{LITERT_BASE}/v1/models", timeout=timeout)
        if r.status_code != 200:
            return []
        data = r.json() or {}
        out = []
        for m in data.get("data") or []:
            mid = (m or {}).get("id")
            if mid:
                out.append(str(mid))
        return out
    except Exception:
        return []


def resolve_model_id(preferred: str | None = None) -> str:
    models = list_models()
    pref = preferred or DEFAULT_MODEL
    if pref in models:
        return pref
    for m in models:
        if "e4b" in m.lower():
            return m
    if models:
        return models[0]
    return pref


def _lang_name(code: str) -> str:
    return LANG_NAMES.get(code, code)


def _block_context_hint(label: str | None) -> str:
    lab = (label or "").strip().lower()
    if lab.startswith("diálogo") or lab.startswith("dialogo"):
        return "in-game story dialogue or narration (action/adventure RPG)"
    if lab.startswith("party"):
        return "party roster / character names UI"
    if lab.startswith("ubicación") or lab.startswith("ubicacion"):
        return "location name bar"
    if lab.startswith("título") or lab.startswith("titulo"):
        return "UI title (short label)"
    return "on-screen game text"


def _disambiguation_rules(source: str, target: str) -> str:
    tgt = _lang_name(target)
    lines = [
        "Read the ENTIRE passage first. Infer scene type: combat, chase, calm dialogue, "
        "menu, inventory, location name, party roster.",
        f"Choose {tgt} word senses from SCENE CONTEXT, not the most common dictionary entry.",
        "Mirror source grammar: preserve singular/plural and verb count; do not add extra "
        "verbs or -ando/-iendo participles unless the source supports them.",
        "One source verb → one target verb for the same subject and moment.",
        "Homographs: pick sense from action/emotion/UI role in the scene (speech verbs, "
        "physical reaction vs introspective wording, run vs rain, play music vs play a game).",
        "Preserve in-world terminology (fantasy religion, items, places); do not replace "
        "with generic modern equivalents when the source uses a specific term.",
        "Keep proper nouns unchanged (character/place names).",
    ]
    return "\n".join(f"- {ln}" for ln in lines)


def build_system_prompt(source: str, target: str) -> str:
    src = _lang_name(source)
    tgt = _lang_name(target)
    return (
        f"You are an expert video-game localizer ({src} → {tgt}). "
        "Input is OCR from on-screen game text.\n\n"
        f"{_disambiguation_rules(source, target)}\n\n"
        "Output rules (STRICT):\n"
        f"- Output ONLY the {tgt} translation.\n"
        "- Keep punctuation, numbers, symbols, and line breaks.\n"
        "- Do not invent facts. No notes or English leftovers."
    )


def build_review_system_prompt(source: str, target: str) -> str:
    src = _lang_name(source)
    tgt = _lang_name(target)
    return (
        f"You are a senior video-game localization QA reviewer ({src} → {tgt}). "
        "You receive the OCR source and a draft translation.\n\n"
        "Fix the draft ONLY when it:\n"
        "- Mismatches singular/plural vs the source\n"
        "- Adds verbs or participles not supported by the source "
        "(one source verb → one target verb)\n"
        "- Uses the wrong homograph sense for the scene (action vs emotion, UI vs narrative, "
        "physical reaction vs introspective)\n"
        "- Replaces in-world/fantasy terms with generic modern equivalents\n"
        "- Omits or invents facts\n"
        "- Leaves English words untranslated in the draft (translate them to "
        f"{tgt} unless they are proper nouns)\n"
        "- Propagates obvious OCR misreads from the source (e.g. Seck→Seek, Lonly→Lonely); "
        "infer the intended English from context, then fix the translation\n\n"
        "If the draft is faithful, return it unchanged.\n"
        f"Output ONLY the final {tgt} translation. No notes or English."
    )


def build_review_user_prompt(
    source_text: str,
    draft: str,
    source: str,
    target: str,
) -> str:
    src = _lang_name(source)
    tgt = _lang_name(target)
    return (
        f"SOURCE ({src}):\n{(source_text or '').strip()}\n\n"
        f"DRAFT ({tgt}):\n{(draft or '').strip()}"
    )


def build_translate_prompt(
    text: str,
    source: str,
    target: str,
    *,
    block_label: str | None = None,
) -> str:
    hint = _block_context_hint(block_label)
    header = f"Context: {hint}."
    if block_label and block_label.strip():
        header = f"Context: [{block_label.strip()}] — {hint}."
    return f"{header}\n\n{(text or '').strip()}"


_BLOCK_SEP = "\n<<<§>>>\n"


def _split_batch_translation(translated: str, n: int) -> list[str]:
    if n <= 1:
        return [translated.strip()]
    if _BLOCK_SEP.strip() in translated:
        parts = [p.strip() for p in translated.split(_BLOCK_SEP.strip())]
        if len(parts) == n:
            return parts
    if _BLOCK_SEP in translated:
        parts = [p.strip() for p in translated.split(_BLOCK_SEP)]
        if len(parts) == n:
            return parts
    if n == len([p for p in translated.split("\n\n") if p.strip()]):
        return [p.strip() for p in translated.split("\n\n") if p.strip()]
    return [translated.strip()] + [""] * (n - 1)


def scrub_translation(out: str) -> str:
    import re

    text = (out or "").strip().strip('"').strip("'")
    for prefix in (
        "Translation:",
        "Traducción:",
        "Translated text:",
        "OCR:",
        "Result:",
        "ES:",
        "Spanish:",
    ):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix) :].strip()
    text = re.sub(
        r"^\[(Diálogo|Dialogo|Party|Ubicación|Ubicacion|Título|Titulo[^\]]*)\]\s*",
        "",
        text,
        flags=re.M | re.I,
    )
    text = re.sub(r"\s*\(([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s'’-]{1,40})\)", "", text)
    text = re.sub(r"\s*=\s*[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{0,40}$", "", text, flags=re.M)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def review_translation(
    source_text: str,
    draft: str,
    source: str,
    target: str,
    *,
    model: str | None = None,
    timeout: float = 45.0,
    max_tokens: int = 512,
) -> str:
    """Segunda pasada: el modelo compara borrador vs source (QA general)."""
    if not (source_text or "").strip() or not (draft or "").strip():
        return draft or ""
    if not is_server_running():
        return draft
    reviewed, err = gemma_generate(
        build_review_user_prompt(source_text, draft, source, target),
        system=build_review_system_prompt(source, target),
        temperature=0.08,
        max_tokens=max_tokens,
        model=model,
        timeout=timeout,
        reasoning_effort=REASONING_REVIEW,
    )
    if err or not (reviewed or "").strip():
        return draft
    return scrub_translation(reviewed)


def _litert_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.12,
    max_tokens: int = 512,
    model: str | None = None,
    timeout: float = 60.0,
    reasoning_effort: str | None = None,
) -> tuple[str | None, str | None]:
    if not is_server_running():
        return None, (
            "Error: Gemma (LiteRT) no está en marcha. "
            "Usá 'Iniciar' en Traductor o Guía."
        )
    mid = model or resolve_model_id()
    payload: dict = {
        "model": mid,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if reasoning_effort is not None:
        payload["reasoning_effort"] = reasoning_effort
    try:
        r = requests.post(
            f"{LITERT_BASE}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=timeout,
        )
    except requests.exceptions.Timeout:
        return None, "Error: Timeout al consultar Gemma."
    except requests.RequestException as e:
        return None, f"Error al consultar Gemma: {e}"
    if r.status_code >= 400:
        return None, f"Error {r.status_code}: {(r.text or '')[:200]}"
    data = r.json() or {}
    choices = data.get("choices") or []
    if not choices:
        return None, "Error: Gemma no devolvió respuesta."
    msg = (choices[0].get("message") or {}) or {}
    content = msg.get("content") or ""
    return str(content).strip(), None


def gemma_generate(
    prompt: str,
    *,
    system: str | None = None,
    temperature: float = 0.15,
    max_tokens: int = 512,
    model: str | None = None,
    timeout: float = 60.0,
    reasoning_effort: str | None = REASONING_TRANSLATE,
) -> tuple[str | None, str | None]:
    """Generación genérica (guía). Devuelve (texto, error)."""
    if not (prompt or "").strip():
        return "", None
    if not is_server_running():
        return None, (
            "Error: Gemma (LiteRT) no está en marcha. "
            "Usá 'Iniciar' en Traductor o Guía."
        )
    mid = model or resolve_model_id()
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt.strip()})
    return _litert_chat(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        model=mid,
        timeout=timeout,
        reasoning_effort=reasoning_effort,
    )


_QUERY_KEYWORDS_PROMPT = """Translate the player's game question into short English search keywords for a walkthrough guide.
Reply with ONLY comma-separated English keywords (location names, dungeons, bosses, items).
No sentences. If already English, return the key terms only.

QUESTION: {query}
"""


def translate_query_keywords(
    query: str,
    *,
    timeout: float = 12.0,
) -> list[str]:
    """Términos EN para buscar en guías (modo rápido, sin revisión)."""
    if not (query or "").strip() or not is_server_running():
        return []
    raw, err = gemma_generate(
        _QUERY_KEYWORDS_PROMPT.format(query=query.strip()),
        temperature=0.0,
        max_tokens=48,
        timeout=timeout,
        reasoning_effort=REASONING_SEARCH,
    )
    if err or not (raw or "").strip():
        return []
    import re

    parts = re.split(r"[,;\n]+", raw.strip())
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        t = re.sub(r"[^a-zA-Z0-9\s\-']", "", p).strip().lower()
        if not t or len(t) < 3 or t in seen:
            continue
        seen.add(t)
        out.append(t)
        for word in t.split():
            if len(word) >= 3 and word not in seen:
                seen.add(word)
                out.append(word)
    return out


def _translate_pass(
    text: str,
    source: str,
    target: str,
    *,
    model: str | None = None,
    timeout: float = 45.0,
    max_tokens: int = 512,
    block_label: str | None = None,
) -> str:
    """Primera pasada: localización con thinking medium."""
    if not (text or "").strip():
        return ""
    messages = [
        {"role": "system", "content": build_system_prompt(source, target)},
        {
            "role": "user",
            "content": build_translate_prompt(
                text, source, target, block_label=block_label
            ),
        },
    ]
    raw, err = _litert_chat(
        messages,
        temperature=0.12,
        max_tokens=max_tokens,
        model=model,
        timeout=timeout,
        reasoning_effort=REASONING_TRANSLATE,
    )
    if err:
        raise RuntimeError(err)
    if not (raw or "").strip():
        raise RuntimeError("LiteRT no devolvió traducción.")
    return scrub_translation(raw)


def translate_blocks(
    blocks: list,
    source: str = "en",
    target: str = "es",
    *,
    model: str | None = None,
    timeout: float = 30.0,
) -> list[dict]:
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

    def _row(block, label: str, src_text: str, translated: str) -> dict:
        return {
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

    if len(normalized) == 1:
        src_text, label, block = normalized[0]
        try:
            draft = _translate_pass(
                src_text,
                source,
                target,
                model=model,
                timeout=timeout,
                max_tokens=512,
                block_label=label,
            )
            translated = review_translation(
                src_text,
                draft,
                source,
                target,
                model=model,
                timeout=timeout,
                max_tokens=512,
            )
        except Exception as e:
            translated = f"[Error: {e}]"
        return [_row(block, label, src_text, translated)]

    combined = _BLOCK_SEP.join(src for src, _, _ in normalized)
    batch_extra = (
        f"\n\nIMPORTANT: The input has {len(normalized)} sections separated by "
        f"the exact marker {_BLOCK_SEP.strip()!r}. "
        f"Keep that marker unchanged between sections in your {_lang_name(target)} output. "
        "Do NOT add section labels in the output."
    )
    try:
        batch_translated = _translate_pass(
            combined + batch_extra,
            source,
            target,
            model=model,
            timeout=max(timeout, 45.0),
            max_tokens=min(2048, 256 + len(combined) * 2),
            block_label="Diálogo",
        )
        parts = _split_batch_translation(batch_translated, len(normalized))
    except Exception as e:
        parts = [f"[Error: {e}]"] * len(normalized)

    out: list[dict] = []
    for (src_text, label, block), translated in zip(normalized, parts):
        reviewed = review_translation(
            src_text,
            translated or "",
            source,
            target,
            model=model,
            timeout=timeout,
            max_tokens=min(512, 128 + len(src_text) * 2),
        )
        out.append(_row(block, label, src_text, reviewed))
    return out


def translate_text(
    text: str,
    source: str = "en",
    target: str = "es",
    *,
    model: str | None = None,
    timeout: float = 45.0,
    max_tokens: int = 512,
    block_label: str | None = None,
    review: bool = True,
) -> str:
    if not (text or "").strip():
        return ""
    if not is_server_running():
        raise RuntimeError(
            "Gemma (LiteRT) no está en marcha. Usá 'Iniciar' en Traductor o Guía."
        )
    clean = _translate_pass(
        text,
        source,
        target,
        model=model,
        timeout=timeout,
        max_tokens=max_tokens,
        block_label=block_label,
    )
    if not review:
        return clean
    return review_translation(
        text,
        clean,
        source,
        target,
        model=model,
        timeout=timeout,
        max_tokens=max_tokens,
    )


def list_imported_models(timeout: float = 30.0) -> list[str]:
    exe = find_litert_lm()
    if not exe:
        return []
    try:
        r = subprocess.run(
            [exe, "list"], capture_output=True, text=True, timeout=timeout
        )
        if r.returncode != 0:
            return []
        ids: list[str] = []
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if not line or line.startswith("Listing") or line.startswith("ID"):
                continue
            token = line.split()[0]
            if token not in ("ID", "SIZE", "MODIFIED"):
                ids.append(token)
        return ids
    except Exception:
        return []


def delete_imported_model(model_id: str) -> None:
    exe = find_litert_lm()
    if not exe:
        raise RuntimeError("litert-lm no está instalado.")
    mid = (model_id or "").strip()
    if not mid:
        raise ValueError("ID de modelo vacío")
    r = subprocess.run(
        [exe, "delete", mid],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()[:500]
        raise RuntimeError(err or f"No se pudo borrar {mid}")


def purge_legacy_models() -> list[str]:
    """Elimina modelos viejos (p. ej. gemma4-e2b)."""
    removed: list[str] = []
    for mid in LEGACY_MODELS:
        if mid not in list_imported_models():
            continue
        try:
            delete_imported_model(mid)
            removed.append(mid)
        except Exception:
            pass
    return removed


class LiteRTManager:
    """Arranque / parada del servidor litert-lm serve."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._backend: str = get_preferred_backend()

    def is_installed(self) -> bool:
        return find_litert_lm() is not None

    def is_running(self) -> bool:
        return is_server_running()

    def start_server(
        self,
        progress: Callable[[str], None] | None = None,
        backend: str | None = None,
    ) -> bool:
        if self.is_running():
            if progress:
                progress("Gemma (LiteRT) ya está en marcha.")
            return True
        exe = find_litert_lm()
        if not exe:
            raise RuntimeError(
                "No encontré litert-lm. Ejecutá Setup_Gemma_LiteRT.bat."
            )
        b = backend or get_preferred_backend()
        cfg_path = write_litert_config(b)
        self._backend = b
        if progress:
            progress(
                f"Iniciando LiteRT ({BACKEND_LABELS.get(b, b)})…"
            )
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW
        with self._lock:
            self._proc = subprocess.Popen(
                [
                    exe,
                    "serve",
                    "--host",
                    LITERT_HOST,
                    "--port",
                    str(LITERT_PORT),
                    "--config",
                    str(cfg_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        import time

        for _ in range(40):
            if self.is_running():
                if progress:
                    progress("Gemma (LiteRT) listo.")
                return True
            time.sleep(0.5)
            if self._proc.poll() is not None:
                break
        raise RuntimeError(
            "LiteRT no respondió en el puerto 9379. "
            f"¿Importaste {DEFAULT_MODEL}? (Setup Gemma)"
        )

    def stop_server(self) -> dict:
        killed: list[str] = []
        errors: list[str] = []
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW
            for name in ("litert-lm.exe", "litert_lm.exe"):
                try:
                    r = subprocess.run(
                        ["taskkill", "/F", "/IM", name, "/T"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        creationflags=creationflags,
                    )
                    if r.returncode == 0:
                        killed.append(name)
                except Exception as e:
                    errors.append(str(e))
        else:
            try:
                r = subprocess.run(
                    ["pkill", "-f", "litert-lm serve"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if r.returncode == 0:
                    killed.append("litert-lm")
            except Exception as e:
                errors.append(str(e))
        with self._lock:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=3)
                    except Exception:
                        self._proc.kill()
                    killed.append("managed-process")
                except Exception as e:
                    errors.append(str(e))
            self._proc = None
        return {"killed": killed, "errors": errors}

    def import_model(
        self,
        progress: Callable[[str], None] | None = None,
        model_id: str | None = None,
    ) -> None:
        exe = find_litert_lm()
        if not exe:
            raise RuntimeError("litert-lm no está instalado.")
        mid = model_id or DEFAULT_MODEL
        preset = MODEL_PRESETS.get(mid)
        if not preset:
            raise RuntimeError(f"Modelo desconocido: {mid}")
        purge_legacy_models()
        try:
            listed = subprocess.run(
                [exe, "list"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if listed.returncode == 0 and mid in (listed.stdout or ""):
                if progress:
                    progress(f"Modelo {mid} ya importado.")
                return
        except Exception:
            pass
        if progress:
            progress(
                f"Descargando/importando {mid} ({preset.get('size_hint', '?')})…"
            )
        r = subprocess.run(
            [
                exe,
                "import",
                "--from-huggingface-repo",
                preset["hf_repo"],
                preset["file"],
                mid,
            ],
            capture_output=True,
            text=True,
            timeout=3600,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()[:500]
            raise RuntimeError(f"Fallo al importar modelo: {err or r.returncode}")
        if progress:
            progress(f"Modelo {mid} listo.")

    def list_imported_models(self) -> list[str]:
        return list_imported_models()

    def delete_model(self, model_id: str) -> None:
        if self.is_running():
            self.stop_server()
        delete_imported_model(model_id)

    def purge_legacy_models(self) -> list[str]:
        if self.is_running():
            self.stop_server()
        return purge_legacy_models()
