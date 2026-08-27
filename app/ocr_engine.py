"""Router OCR multi-motor (OneOCR / EasyOCR / WinRT) + clustering de bloques."""

from __future__ import annotations

import asyncio
import math
import re
import time

from PIL import Image

from .ocr_backends import EasyOcrBackend, OneOcrBackend, WinRtBackend
from .ocr_types import (
    LETTER_RE,
    MAX_BLOCKS,
    OCR_LANGUAGE_CANDIDATES,
    OcrLineBox,
    TextBlock,
    UPSCALE,
)

# Re-export tipos para compat
__all__ = [
    "OCREngine",
    "OcrLineBox",
    "TextBlock",
    "cluster_blocks",
    "label_blocks",
    "filter_game_ui_blocks",
    "preprocess_variants",
    "UPSCALE",
    "WINDOWS_OCR_AVAILABLE",
    "ENGINE_IDS",
    "ENGINE_LABELS",
    "_is_noise_block",
    "_is_title_text",
]

# Re-export para compat tests / imports viejos
WINDOWS_OCR_AVAILABLE = False
try:
    from .ocr_backends.winrt_backend import WINDOWS_OCR_AVAILABLE as _WINRT
except ImportError:
    _WINRT = False
WINDOWS_OCR_AVAILABLE = _WINRT

ENGINE_IDS = ("oneocr", "easyocr", "winrt")
FALLBACK_ORDER = ("oneocr", "easyocr", "winrt")
ENGINE_LABELS = {
    "oneocr": "OneOCR",
    "easyocr": "EasyOCR",
    "winrt": "Windows OCR",
}


def _median(vals: list[float]) -> float:
    if not vals:
        return 1.0
    s = sorted(vals)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _is_title_text(text: str, next_text: str | None = None) -> bool:
    """Título corto (heurística IsTitleData + IsContextTitle)."""
    t = (text or "").strip()
    if not t:
        return True
    if (t.startswith("[") and t.endswith("]")) or (
        t.startswith("【") and t.endswith("】")
    ):
        return True
    if t.endswith(":") or t.endswith("："):
        return True
    cc = _char_count(t)
    words = len(t.split())
    if cc <= 10 and words <= 3:
        if next_text:
            ncc = _char_count(next_text)
            if ncc >= math.ceil(cc * 1.5):
                return True
        else:
            return True
    return False


def _is_ui_chrome_block(b: TextBlock, all_blocks: list[TextBlock]) -> bool:
    """Logos, títulos de UI y ruido lateral — no traducir ni overlay."""
    text = (b.text or "").strip()
    if not text:
        return True

    others = [x for x in all_blocks if x is not b]
    my_cc = _char_count(text)
    max_cc = max((_char_count(x.text) for x in others), default=0)

    if _is_title_text(text) and max_cc >= my_cc * 3:
        return True

    img_w = max(
        float(b.img_w or 0),
        max((x.x + x.w for x in all_blocks), default=1.0),
        1.0,
    )
    img_h = max(
        float(b.img_h or 0),
        max((x.y + x.h for x in all_blocks), default=1.0),
        1.0,
    )
    cx = (b.x + b.w / 2) / img_w
    cy = (b.y + b.h / 2) / img_h

    # Barra lateral (REALMS / ARKANIA en Realms of Arkania)
    if cx > 0.58 and my_cc <= 24 and len(text.split()) <= 4:
        return True
    # Título decorativo arriba con cuerpo largo debajo
    if cy < 0.22 and my_cc <= 16 and max_cc > my_cc * 2:
        return True
    # Una palabra en mayúsculas suelta
    if (
        text.isupper()
        and len(text.split()) == 1
        and my_cc <= 12
        and max_cc > my_cc * 2
    ):
        return True
    return False


def filter_game_ui_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    if not blocks:
        return []
    return [b for b in blocks if not _is_ui_chrome_block(b, blocks)]


def _looks_like_party_roster(text: str) -> bool:
    """Nombres cortos del party — no narración de diálogo."""
    t = (text or "").strip()
    if not t or len(t) > 90:
        return False
    if any(ch in t for ch in ".!?"):
        return False
    lines = [ln.strip() for ln in t.split("\n") if ln.strip()]
    if not lines or len(lines) > 8:
        return False
    return all(len(ln.split()) <= 3 and len(ln) <= 22 for ln in lines)


def merge_dialogue_fragments(blocks: list[TextBlock]) -> list[TextBlock]:
    """Une trozos del mismo cuadro de diálogo partidos por OCR."""
    if len(blocks) < 2:
        return blocks

    ordered = sorted(blocks, key=lambda b: (b.y, b.x))
    merged: list[TextBlock] = [ordered[0]]
    for b in ordered[1:]:
        prev = merged[-1]
        if _looks_like_party_roster(b.text) or _looks_like_party_roster(prev.text):
            merged.append(b)
            continue
        gap = b.y - (prev.y + prev.h)
        line_h = max(prev.h / max(prev.text.count("\n") + 1, 1), b.h, 8.0)
        same_col = abs(b.x - prev.x) <= line_h * 2.5
        close = gap <= line_h * 3.0
        if same_col and close:
            merged[-1] = TextBlock(
                text=f"{prev.text}\n{b.text}".strip(),
                x=min(prev.x, b.x),
                y=min(prev.y, b.y),
                w=max(prev.x + prev.w, b.x + b.w) - min(prev.x, b.x),
                h=max(prev.y + prev.h, b.y + b.h) - min(prev.y, b.y),
                img_w=prev.img_w or b.img_w,
                img_h=prev.img_h or b.img_h,
            )
        else:
            merged.append(b)
    return merged


def cluster_blocks(
    lines: list[OcrLineBox],
    gap_ratio: float = 0.45,
    image_height: float | None = None,
) -> list[TextBlock]:
    if not lines:
        return []

    ordered = sorted(lines, key=lambda ln: (ln.y, ln.x))
    heights = [ln.h for ln in ordered if ln.h > 0]
    med_h = max(1.0, _median(heights))
    gap_cut = gap_ratio * med_h

    groups: list[list[OcrLineBox]] = [[ordered[0]]]
    for ln in ordered[1:]:
        prev = groups[-1][-1]
        gap = ln.y - (prev.y + prev.h)
        h_ratio = max(ln.h, prev.h) / max(min(ln.h, prev.h), 1.0)
        if gap > gap_cut or h_ratio > 1.2:
            groups.append([ln])
        else:
            groups[-1].append(ln)

    merged_groups: list[list[OcrLineBox]] = []
    for group in groups:
        if not merged_groups:
            merged_groups.append(group)
            continue
        prev = merged_groups[-1]
        py0 = min(l.y for l in prev)
        py1 = max(l.y + l.h for l in prev)
        gy0 = min(l.y for l in group)
        gy1 = max(l.y + l.h for l in group)
        overlap = max(0.0, min(py1, gy1) - max(py0, gy0))
        min_h = max(1.0, min(py1 - py0, gy1 - gy0))
        px1 = max(l.x + l.w for l in prev)
        gx0 = min(l.x for l in group)
        near_x = gx0 - px1 < med_h * 4
        if overlap / min_h >= 0.5 and near_x:
            merged_groups[-1] = prev + group
        else:
            merged_groups.append(group)

    blocks: list[TextBlock] = []
    for group in merged_groups:
        group = sorted(group, key=lambda ln: (ln.y, ln.x))
        text = "\n".join(ln.text.strip() for ln in group if ln.text.strip()).strip()
        if not text:
            continue
        x0 = min(ln.x for ln in group)
        y0 = min(ln.y for ln in group)
        x1 = max(ln.x + ln.w for ln in group)
        y1 = max(ln.y + ln.h for ln in group)
        blocks.append(TextBlock(text=text, x=x0, y=y0, w=x1 - x0, h=y1 - y0))

    return label_blocks(_cap_blocks(blocks), image_height)


def _cap_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    while len(blocks) > MAX_BLOCKS:
        best_i = 0
        best_gap = float("inf")
        for i in range(len(blocks) - 1):
            gap = blocks[i + 1].y - (blocks[i].y + blocks[i].h)
            if gap < best_gap:
                best_gap = gap
                best_i = i
        a, b = blocks[best_i], blocks[best_i + 1]
        merged = TextBlock(
            text=f"{a.text}\n{b.text}".strip(),
            x=min(a.x, b.x),
            y=min(a.y, b.y),
            w=max(a.x + a.w, b.x + b.w) - min(a.x, b.x),
            h=max(a.y + a.h, b.y + b.h) - min(a.y, b.y),
        )
        blocks = blocks[:best_i] + [merged] + blocks[best_i + 2 :]
    return blocks


def label_blocks(blocks: list[TextBlock], image_height: float | None = None) -> list[TextBlock]:
    if not blocks:
        return []
    if len(blocks) == 1:
        blocks[0].label = (
            "Título" if _is_title_text(blocks[0].text) else "Texto"
        )
        return blocks

    img_h = image_height or max(b.y + b.h for b in blocks)
    img_h = max(img_h, 1.0)

    meaningful = [b for b in blocks if not _is_ui_chrome_block(b, blocks)]
    if not meaningful:
        meaningful = list(blocks)

    def _dialogue_score(b: TextBlock) -> float:
        cc = _char_count(b.text)
        cy = (b.y + b.h / 2) / img_h
        zone = 0.35 if cy < 0.15 else (0.75 if cy > 0.85 else 1.0)
        title_pen = 0.05 if _is_title_text(b.text) else 1.0
        return cc * zone * title_pen

    dialog_block = max(meaningful, key=_dialogue_score)
    dialog_id = id(dialog_block)

    labeled: list[TextBlock] = []
    used_location = False
    party_n = 0
    text_n = 0
    title_n = 0

    sorted_by_y = sorted(blocks, key=lambda x: x.y)
    for b in sorted_by_y:
        if _is_ui_chrome_block(b, blocks):
            title_n += 1
            b.label = "Título" if title_n == 1 else f"Título {title_n}"
        elif id(b) == dialog_id:
            b.label = "Diálogo"
        elif (b.y + b.h / 2) / img_h > 0.78 and _looks_like_party_roster(b.text):
            party_n += 1
            b.label = "Party" if party_n == 1 else f"Party {party_n}"
        elif (
            not used_location
            and 0.35 <= (b.y + b.h / 2) / img_h <= 0.75
            and b.w / max(b.h, 1.0) > 3.5
            and b.h < img_h * 0.12
        ):
            b.label = "Ubicación"
            used_location = True
        else:
            text_n += 1
            b.label = f"Texto {text_n}"
        labeled.append(b)
    return labeled


def _is_noise_block(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 2:
        return True
    letters = LETTER_RE.findall(t)
    return len(letters) < 2


def upscale_for_ocr(image: Image.Image, factor: int = UPSCALE) -> Image.Image:
    if factor <= 1:
        return image
    w, h = image.size
    return image.resize((w * factor, h * factor), Image.Resampling.LANCZOS)


def preprocess_variants(image: Image.Image) -> list[Image.Image]:
    from PIL import ImageEnhance, ImageFilter, ImageOps

    base = image.convert("RGB")
    variants: list[Image.Image] = []
    variants.append(upscale_for_ocr(base, UPSCALE))

    gray = ImageOps.grayscale(base)
    gray = ImageOps.autocontrast(gray, cutoff=2)
    gray = ImageEnhance.Contrast(gray).enhance(1.6)
    gray_rgb = gray.convert("RGB")
    variants.append(upscale_for_ocr(gray_rgb, UPSCALE))

    for thr in (120, 160):
        bw = gray.point(lambda p, t=thr: 255 if p > t else 0)
        hist = bw.histogram()
        if sum(hist[200:]) > sum(hist[:56]):
            bw = ImageOps.invert(bw)
        bw = bw.filter(ImageFilter.MedianFilter(size=3))
        variants.append(upscale_for_ocr(bw.convert("RGB"), UPSCALE))

    return variants


def preprocess_variants_for(engine_id: str, image: Image.Image) -> list[Image.Image]:
    """OneOCR/EasyOCR: 1 pasada (sin binarizar). WinRT: 4 variantes."""
    if engine_id in ("oneocr", "easyocr"):
        base = image.convert("RGB")
        # x2 alcanza y es ~2× más rápido que x3 × 4 variantes
        return [upscale_for_ocr(base, 2)]
    return preprocess_variants(image)


def _score_ocr_lines(lines: list[OcrLineBox]) -> int:
    score = 0
    for ln in lines:
        letters = LETTER_RE.findall(ln.text or "")
        score += len(letters)
        words = re.findall(r"[A-Za-zÀ-ÿ]{3,}", ln.text or "")
        score += len(words) * 2
    return score


class OCREngine:
    """Router OCR: motor preferido + fallback encadenado."""

    def __init__(self, language_code: str = "en", engine_id: str = "oneocr"):
        self.language_code = language_code
        self.engine_id = engine_id if engine_id in ENGINE_IDS else "oneocr"
        self.last_error = None
        self.last_used_backend_id: str | None = None
        self.last_ocr_seconds: float = 0.0
        self._oneocr = OneOcrBackend(language_code)
        self._easyocr = EasyOcrBackend(language_code)
        self._winrt = WinRtBackend(language_code)

    def _backends(self):
        return {
            "oneocr": self._oneocr,
            "easyocr": self._easyocr,
            "winrt": self._winrt,
        }

    def set_engine(self, engine_id: str) -> None:
        if engine_id in ENGINE_IDS:
            self.engine_id = engine_id

    def set_language(self, language_code: str) -> None:
        self.language_code = language_code
        self._oneocr.set_language(language_code)
        self._easyocr.set_language(language_code)
        self._winrt.set_language(language_code)

    def prepare_oneocr(self) -> bool:
        if not self._oneocr.prepare_dlls():
            return False
        return self._oneocr.warmup()

    def resolve_backend(self):
        backends = self._backends()
        order = [self.engine_id] + [e for e in FALLBACK_ORDER if e != self.engine_id]
        for eid in order:
            b = backends[eid]
            if eid == "oneocr" and not b.is_available():
                continue
            if eid == "easyocr" and not b.is_available():
                continue
            if eid == "winrt" and not b.is_available():
                continue
            self.last_used_backend_id = eid
            return b
        self.last_used_backend_id = None
        return None

    def status_ok(self) -> bool:
        return any(b.is_available() for b in self._backends().values())

    def has_exact_language_pack(self, language_code=None):
        return self._winrt.has_exact_language_pack(language_code or self.language_code)

    def needs_language_pack(self):
        bid = self.last_used_backend_id or self.engine_id
        if bid != "winrt":
            return False
        return self._winrt.is_available() and not self._winrt.has_exact_language_pack(
            self.language_code
        )

    def status_message(self) -> str:
        parts = [
            f"Motor pedido: {ENGINE_LABELS.get(self.engine_id, self.engine_id)}",
            self._oneocr.status_message(),
            self._easyocr.status_message(),
            self._winrt.status_message(),
        ]
        if self.last_used_backend_id:
            parts.insert(1, f"Último usado: {ENGINE_LABELS.get(self.last_used_backend_id)}")
        return "\n".join(parts)

    def _recognize_best_variant(
        self, image: Image.Image, backend
    ) -> tuple[list[OcrLineBox], float, float]:
        best_lines: list[OcrLineBox] = []
        best_score = -1
        best_w = float(image.size[0] * UPSCALE)
        best_h = float(image.size[1] * UPSCALE)
        eid = getattr(backend, "id", "winrt")
        for variant in preprocess_variants_for(eid, image):
            lines = backend.recognize_lines(variant)
            sc = _score_ocr_lines(lines)
            if sc > best_score:
                best_score = sc
                best_lines = lines
                best_w = float(variant.size[0])
                best_h = float(variant.size[1])
        return best_lines, best_w, best_h

    async def extract_blocks_async(self, image: Image.Image) -> list[TextBlock]:
        t0 = time.perf_counter()
        backend = self.resolve_backend()
        if backend is None:
            err = "Ningún motor OCR disponible (OneOCR / EasyOCR / WinRT)"
            self.last_error = err
            self.last_ocr_seconds = time.perf_counter() - t0
            return [TextBlock(text=f"[OCR no disponible] {err}", x=0, y=0, w=0, h=0, label="Error")]

        try:
            best_lines, best_w, best_h = self._recognize_best_variant(image, backend)
            blocks = cluster_blocks(best_lines, image_height=best_h)
            cleaned = [b for b in blocks if not _is_noise_block(b.text)]
            merged = merge_dialogue_fragments(cleaned)
            content = filter_game_ui_blocks(merged)
            if not content and cleaned:
                content = cleaned
            for b in content:
                b.img_w = best_w
                b.img_h = best_h
            self.last_ocr_seconds = time.perf_counter() - t0
            return content
        except Exception as e:
            self.last_error = str(e)
            self.last_ocr_seconds = time.perf_counter() - t0
            return [TextBlock(text=f"[Error OCR: {e}]", x=0, y=0, w=0, h=0, label="Error")]

    async def extract_lines_async(self, image: Image.Image) -> list[OcrLineBox]:
        backend = self.resolve_backend()
        if backend is None:
            return []
        lines, _, _ = self._recognize_best_variant(image, backend)
        return lines

    async def extract_text_async(self, image):
        blocks = await self.extract_blocks_async(image)
        if len(blocks) == 1 and blocks[0].text.startswith(("[OCR no disponible]", "[Error OCR")):
            return blocks[0].text
        return "\n\n".join(b.text for b in blocks if b.text.strip()).strip()

    def extract_lines(self, image) -> list[OcrLineBox]:
        return asyncio.run(self.extract_lines_async(image))

    def extract_blocks(self, image) -> list[TextBlock]:
        return asyncio.run(self.extract_blocks_async(image))

    def extract_text(self, image):
        return asyncio.run(self.extract_text_async(image))
