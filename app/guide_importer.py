from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

MIN_GUIDE_CHARS = 500
MAX_CHAPTERS = 80
CHAPTER_PAUSE_SEC = 0.5
REQUEST_TIMEOUT = 25
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_CHAPTER_RE = re.compile(r"^(?P<prefix>.+)-p(?P<num>\d+)\.php$", re.I)


def _app_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # repo root = parent of package app/
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


GUIDES_DIR = os.path.join(_app_root(), "guias")


class GuideImportError(Exception):
    """Error de usuario (403, URL, texto corto, hub vacío)."""


@dataclass
class ImportResult:
    path: str
    title: str
    adapter: str
    pages: int
    chars: int
    warnings: list[str] = field(default_factory=list)


def validate_http_url(url: str) -> str:
    u = (url or "").strip()
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("La URL debe empezar con http:// o https://")
    return u


def safe_slug(text: str, fallback: str = "guia") -> str:
    raw = (text or "").strip().lower()
    raw = re.sub(r"[^\w\s\-]+", "", raw, flags=re.UNICODE)
    raw = re.sub(r"[\s_]+", "-", raw).strip("-")
    return (raw[:80] or fallback)


def unique_guide_path(guides_dir: str, slug: str) -> str:
    os.makedirs(guides_dir, exist_ok=True)
    base = safe_slug(slug)
    path = os.path.join(guides_dir, f"{base}.txt")
    if not os.path.exists(path):
        return path
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(guides_dir, f"{base}-{stamp}.txt")


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines).strip()


def extract_page_title(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return ""


def is_eliteguias_chapter_url(url: str) -> bool:
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1]
    return bool(_CHAPTER_RE.match(name))


def discover_eliteguias_chapters(hub_url: str, hub_html: str) -> list[str]:
    soup = BeautifulSoup(hub_html or "", "html.parser")
    hub_name = urlparse(hub_url).path.rsplit("/", 1)[-1]
    hub_stem = re.sub(r"\.php$", "", hub_name, flags=re.I)
    found: dict[int, str] = {}
    for a in soup.find_all("a", href=True):
        abs_url = urljoin(hub_url, a["href"])
        name = urlparse(abs_url).path.rsplit("/", 1)[-1]
        m = _CHAPTER_RE.match(name)
        if not m:
            continue
        if m.group("prefix").lower() != hub_stem.lower():
            continue
        num = int(m.group("num"))
        found[num] = abs_url
    return [found[k] for k in sorted(found)]


def detect_adapter(url: str) -> str:
    p = urlparse(url)
    host = (p.netloc or "").lower()
    path = (p.path or "").lower()
    if "eliteguias.com" in host:
        return "eliteguias"
    if "gamefaqs.gamespot.com" in host and "/faqs/" in path:
        return "gamefaqs"
    return "generic"


def extract_gamefaqs_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    pres = soup.find_all("pre")
    best = ""
    for pre in pres:
        t = pre.get_text("\n").strip()
        if len(t) > len(best):
            best = t
    if len(best) >= 200:
        return best
    return html_to_text(html)


class GuideImporter:
    def __init__(
        self,
        guides_dir: str | None = None,
        session: requests.Session | None = None,
    ):
        self.guides_dir = guides_dir or GUIDES_DIR
        self.session = session or requests.Session()

    def fetch(self, url: str) -> tuple[str, str]:
        try:
            r = self.session.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.Timeout as e:
            raise GuideImportError("Timeout al descargar la URL.") from e
        except requests.RequestException as e:
            raise GuideImportError(f"Error de red: {e}") from e
        if r.status_code in (401, 403, 429):
            raise GuideImportError(
                f"El sitio bloqueó la descarga (HTTP {r.status_code}). "
                "Guardá el texto a mano o usá Cargar .txt."
            )
        if r.status_code >= 400:
            raise GuideImportError(f"Error HTTP {r.status_code}")
        r.encoding = r.apparent_encoding or r.encoding or "utf-8"
        return str(r.url), r.text

    def import_url(self, url: str, progress_cb=None) -> ImportResult:
        try:
            url = validate_http_url(url)
        except ValueError as e:
            raise GuideImportError(str(e)) from e

        adapter = detect_adapter(url)
        warnings: list[str] = []
        title = ""
        pages = 0
        text = ""

        if adapter == "eliteguias":
            text, title, pages, warnings = self._import_eliteguias(url, progress_cb)
        elif adapter == "gamefaqs":
            final_url, html = self.fetch(url)
            if progress_cb:
                progress_cb(1, 1, "Descargando GameFAQs")
            title = extract_page_title(html) or safe_slug(
                urlparse(final_url).path.rsplit("/", 1)[-1]
            )
            body = extract_gamefaqs_text(html)
            text = f"# {title}\n\n{body}".strip()
            pages = 1
        else:
            final_url, html = self.fetch(url)
            if progress_cb:
                progress_cb(1, 1, "Descargando página")
            title = extract_page_title(html) or safe_slug(
                urlparse(final_url).path.rsplit("/", 1)[-1], "guia"
            )
            body = html_to_text(html)
            text = f"# {title}\n\n{body}".strip()
            pages = 1

        if len(text) < MIN_GUIDE_CHARS:
            raise GuideImportError(
                f"Texto demasiado corto ({len(text)} chars; mínimo {MIN_GUIDE_CHARS}). "
                "Probá otra URL o usá Cargar .txt."
            )

        slug_source = title or safe_slug(urlparse(url).path.rsplit("/", 1)[-1])
        path = unique_guide_path(self.guides_dir, slug_source)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

        return ImportResult(
            path=path,
            title=title or os.path.basename(path),
            adapter=adapter,
            pages=pages,
            chars=len(text),
            warnings=warnings,
        )

    def _import_eliteguias(
        self, url: str, progress_cb=None
    ) -> tuple[str, str, int, list[str]]:
        warnings: list[str] = []
        final_url, html = self.fetch(url)
        title = extract_page_title(html) or safe_slug(
            urlparse(final_url).path.rsplit("/", 1)[-1]
        )

        if is_eliteguias_chapter_url(url):
            if progress_cb:
                progress_cb(1, 1, "Descargando capítulo")
            body = html_to_text(html)
            text = f"# {title}\n\n## {title}\n\n{body}".strip()
            return text, title, 1, warnings

        chapters = discover_eliteguias_chapters(final_url, html)
        if not chapters:
            raise GuideImportError(
                "No encontré capítulos (-pN.php) en esta página de Eliteguías. "
                "Abrí un índice de guía o un capítulo concreto."
            )

        if len(chapters) > MAX_CHAPTERS:
            warnings.append(
                f"Hub con {len(chapters)} capítulos; se importaron solo {MAX_CHAPTERS}."
            )
            chapters = chapters[:MAX_CHAPTERS]

        parts: list[str] = [f"# {title}\n"]
        total = len(chapters)
        for i, chapter_url in enumerate(chapters, start=1):
            if progress_cb:
                progress_cb(i, total, "Descargando capítulos Eliteguías")
            if i > 1 and CHAPTER_PAUSE_SEC > 0:
                time.sleep(CHAPTER_PAUSE_SEC)
            try:
                _, ch_html = self.fetch(chapter_url)
            except GuideImportError as e:
                accumulated = "\n".join(parts)
                if len(accumulated) >= MIN_GUIDE_CHARS:
                    warnings.append(
                        f"Importación parcial: falló en capítulo {i}/{total} ({e})."
                    )
                    break
                raise GuideImportError(
                    f"Falló al bajar el capítulo {i}/{total}: {e}"
                ) from e

            ch_title = extract_page_title(ch_html) or f"Capítulo {i}"
            ch_body = html_to_text(ch_html)
            parts.append(f"## {ch_title}\n\n{ch_body}\n")

        text = "\n".join(parts).strip()
        return text, title, len(parts) - 1, warnings
