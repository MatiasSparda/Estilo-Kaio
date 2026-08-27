from __future__ import annotations

import re
from dataclasses import dataclass

MAX_BLOCKS = 8
UPSCALE = 3
LETTER_RE = re.compile(r"[A-Za-zÀ-ÿア-ン一-龥가-힣]")

OCR_LANGUAGE_CANDIDATES = {
    "en": ["en-US", "en-GB", "en"],
    "es": ["es-ES", "es-MX", "es"],
    "ja": ["ja", "ja-JP"],
    "ko": ["ko", "ko-KR"],
    "zh-CN": ["zh-Hans", "zh-CN"],
    "zh-TW": ["zh-Hant", "zh-TW"],
    "pt": ["pt-BR", "pt-PT", "pt"],
    "fr": ["fr-FR", "fr"],
    "de": ["de-DE", "de"],
    "it": ["it-IT", "it"],
    "ru": ["ru", "ru-RU"],
    "ar": ["ar-SA", "ar"],
}


@dataclass
class OcrLineBox:
    text: str
    x: float
    y: float
    w: float
    h: float


@dataclass
class TextBlock:
    text: str
    x: float
    y: float
    w: float
    h: float
    label: str = "Texto"
    img_w: float = 0.0
    img_h: float = 0.0
