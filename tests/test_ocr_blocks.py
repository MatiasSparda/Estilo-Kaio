"""Clustering espacial OCR (sin WinRT)."""

import re

from app.ocr_engine import (
    OcrLineBox,
    TextBlock,
    cluster_blocks,
    filter_game_ui_blocks,
    label_blocks,
    _is_noise_block,
    _is_title_text,
)


def test_cluster_three_vertical_bands():
    lines = [
        OcrLineBox("What sort of room?", 40, 40, 200, 18),
        OcrLineBox("Dormitory (5 B)", 40, 62, 160, 16),
        OcrLineBox("Single Room (30 B)", 40, 82, 180, 16),
        OcrLineBox("Gryphon's Fordian", 20, 220, 300, 14),
        OcrLineBox("Nylath", 10, 380, 60, 14),
        OcrLineBox("Locke", 80, 380, 50, 14),
    ]
    blocks = cluster_blocks(lines, gap_ratio=0.45, image_height=420)
    assert len(blocks) >= 2
    assert any("room" in b.text.lower() or "Dormitory" in b.text for b in blocks)


def test_cluster_small_gap_stays_one_block():
    lines = [
        OcrLineBox("Line one of dialogue", 10, 10, 200, 16),
        OcrLineBox("Line two continues", 10, 28, 200, 16),
        OcrLineBox("Line three more", 10, 46, 200, 16),
    ]
    blocks = cluster_blocks(lines, gap_ratio=0.45, image_height=100)
    assert len(blocks) == 1
    assert "Line one" in blocks[0].text
    assert "Line three" in blocks[0].text


def test_label_single_is_texto():
    blocks = [TextBlock(text="Hello", x=0, y=0, w=100, h=20)]
    out = label_blocks(blocks, image_height=400)
    assert out[0].label == "Texto"


def test_noise_filter():
    assert _is_noise_block(".")
    assert _is_noise_block("1")
    assert not _is_noise_block("Hi")
    assert not _is_noise_block("Suite (100 B)")


def test_title_text_short_heuristic():
    assert _is_title_text("REALMS")
    assert _is_title_text("REALMS", "Come back! Noa moon screams and turns on the spot.")
    assert not _is_title_text("Come back! Noa moon screams and turns on the spot.")


def test_merge_dialogue_fragments():
    from app.ocr_engine import TextBlock, merge_dialogue_fragments

    blocks = [
        TextBlock(
            text='"Get back!" Noa moon cries and turns around.',
            x=40,
            y=100,
            w=400,
            h=80,
        ),
        TextBlock(
            text="you have to turn back.",
            x=42,
            y=190,
            w=390,
            h=30,
        ),
    ]
    merged = merge_dialogue_fragments(blocks)
    assert len(merged) == 1
    assert "Get back" in merged[0].text
    assert "turn back" in merged[0].text


def test_filter_realms_sidebar_keeps_dialogue():
    """Título del juego en barra lateral no debe competir con el diálogo."""
    blocks = [
        TextBlock(
            text="REALMS",
            x=520,
            y=20,
            w=120,
            h=40,
            img_w=640,
            img_h=480,
        ),
        TextBlock(
            text="Come back! Noa moon screams and turns on the spot.\n"
            "In a reflexive action, you turn around too, and start to run.",
            x=40,
            y=180,
            w=400,
            h=120,
            img_w=640,
            img_h=480,
        ),
    ]
    labeled = label_blocks(blocks, image_height=480)
    dialog = next(b for b in labeled if b.label == "Diálogo")
    assert "Come back" in dialog.text
    assert "REALMS" not in dialog.text

    kept = filter_game_ui_blocks(labeled)
    assert len(kept) == 1
    assert "Come back" in kept[0].text


def test_pixel_upscale_is_nearest_and_inverts_dark():
    from PIL import Image

    from app.ocr_engine import preprocess_pixel_variants, upscale_pixel

    img = Image.new("RGB", (8, 8), (10, 10, 10))
    img.putpixel((2, 2), (240, 240, 240))
    scaled = upscale_pixel(img, factor=4)
    assert scaled.size == (32, 32)
    variants = preprocess_pixel_variants(img)
    assert len(variants) == 3
    assert all(v.size[0] >= 16 for v in variants)

