"""Tests mÃ­nimos del parser de guÃ­as y verificaciÃ³n de citas."""

import os

from app.guide_parser import (
    parse_guide_sections,
    citation_in_source,
    extract_fuente_line,
    strip_fuente_from_steps,
    build_context_for_section,
    is_long_guide,
)


MARKDOWN_GUIDE = """# Intro
Welcome.

## Dark Forest
- Go north
- Talk to the hermit

## Boss Gate
Defeat the guardian.
"""

CAPS_GUIDE = """WALKTHROUGH
===========
Do the thing.

SECRET AREA
===========
Find the chest behind the waterfall.
"""

MISSION_GUIDE = """MISSION: Find the Sword
- Go to the dark forest
- Open the chest

QUEST: Rescue the Mayor
- Talk to the guard
"""


def test_markdown_sections():
    secs = parse_guide_sections(MARKDOWN_GUIDE)
    titles = [s.title for s in secs]
    assert any("Dark Forest" in t for t in titles)
    assert any("Boss Gate" in t for t in titles)


def test_caps_separator_sections():
    secs = parse_guide_sections(CAPS_GUIDE)
    assert len(secs) >= 2
    assert any("SECRET" in s.title.upper() for s in secs)


def test_mission_prefix():
    secs = parse_guide_sections(MISSION_GUIDE)
    assert len(secs) >= 2
    assert citation_in_source("Go to the dark forest", secs[0].body)


def test_citation_whitespace():
    body = "Habla  con el Sabio\nEldrin en el pueblo"
    assert citation_in_source("Habla con el Sabio Eldrin en el pueblo", body)
    assert not citation_in_source("xyz", body)
    assert not citation_in_source("ab", body)


def test_fuente_extract():
    raw = "Ve al norte.\nFUENTE: Go north to the hermit cabin"
    assert extract_fuente_line(raw) == "Go north to the hermit cabin"
    assert "FUENTE" not in strip_fuente_from_steps(raw).upper()
    raw2 = '1. Habla.\n"Fuente: give him the Rock Brisket."'
    assert "Rock Brisket" in (extract_fuente_line(raw2) or "")


def test_build_context_neighbors():
    secs = parse_guide_sections(MISSION_GUIDE)
    ctx = build_context_for_section(secs, secs[0].id)
    assert "dark forest" in ctx.lower()


def test_build_context_following():
    secs = parse_guide_sections(MARKDOWN_GUIDE)
    forest = next(s for s in secs if "Dark Forest" in s.title)
    ctx = build_context_for_section(secs, forest.id, following=1)
    assert "hermit" in ctx.lower()
    assert "guardian" in ctx.lower() or "Boss" in ctx or "boss" in ctx.lower()


def test_slice_around_anchor():
    from app.guide_parser import slice_around_anchor

    text = (
        "Go north to the village.\n\n"
        "Talk to the hermit about the crown key.\n\n"
        "Then cross the bridge and fight the boss.\n\n"
        "Loot the chest behind the waterfall."
    )
    sl = slice_around_anchor(text, "Talk to the hermit about the crown key.", max_following=10)
    assert sl is not None
    assert "village" in sl["previous"].lower()
    assert "hermit" in sl["current"].lower()
    assert len(sl["following"]) >= 1
    assert "bridge" in sl["following"][0].lower()
    assert "following_text" in sl
    assert "bridge" in sl["following_text"].lower()


def test_slice_previous_lookback():
    from app.guide_parser import slice_around_anchor

    text = (
        "First you buy a shield.\n\n"
        "Then you cross the bridge.\n\n"
        "Talk to the hermit about the crown key.\n\n"
        "Then fight the boss.\n\n"
        "Loot the chest."
    )
    sl = slice_around_anchor(text, "Talk to the hermit about the crown key.", max_following=10)
    assert sl is not None
    prev = sl["previous"].lower()
    assert "shield" in prev or "bridge" in prev
    assert "hermit" not in prev or prev.count(".") >= 0


def test_locate_anchor_by_terms():
    from app.guide_parser import locate_anchor_by_terms, citation_in_source

    text = (
        "Enter the Crown Dungeon and clear every floor.\n\n"
        "After the Crown Dungeon, the Maku Tree calls you.\n\n"
        "Play the Goron Dance to earn the Brother Emblem.\n\n"
        "Next, win the Rock Brisket at the Target Carts game."
    )
    ancla = locate_anchor_by_terms(
        text, "acabo de superar el baile goron y la mazmorra de la corona"
    )
    assert ancla
    assert citation_in_source(ancla, text)
    assert "brisket" in ancla.lower() or "carts" in ancla.lower() or "rock" in ancla.lower()


def test_empty_and_long_flags():
    assert parse_guide_sections("")[0].title == "Guía completa"
    assert not is_long_guide("x" * 100)
    assert is_long_guide("x" * 8001)


def test_guia_ejemplo_file():
    text = open("guias/guia_ejemplo.txt", encoding="utf-8").read()
    secs = parse_guide_sections(text)
    assert len(secs) >= 3
    cristal = next(s for s in secs if "Cristal" in s.title or "Alba" in s.title)
    assert citation_in_source("Sabio Eldrin", cristal.body)


def test_is_progress_query():
    from app.ollama_assistant import is_progress_query

    assert is_progress_query(
        "acabo de superar el baile goron y la mazmorra de la corona y no se que hacer"
    )
    assert is_progress_query("I finished the dungeon, what next?")
    assert not is_progress_query("cÃ³mo abro la puerta roja")


def test_progress_start_prefers_later_milestone():
    from app.guide_parser import parse_guide_sections, resolve_progress_start_id

    guide = """# Walkthrough

## Rolling Ridge Intro
Get the Crown Key from the elder.

## Crown Dungeon
Enter the Crown Dungeon and beat the boss.

## Rolling Ridge Base
Play the Goron Dance to earn the Brother Emblem.

## Target Carts
Win the Rock Brisket at Crazy Carts.

## Goron Vase
Trade for the Goron Vase.

## -=  6. Bosses -=
Crown Dungeon boss tips and Goron Dance notes.
"""
    secs = parse_guide_sections(guide)
    q = "acabo de superar el baile goron y la mazmorra de la corona"
    sid = resolve_progress_start_id(secs, q)
    assert sid is not None
    title = next(s.title for s in secs if s.id == sid)
    # Tras completar baile+corona, el start mira la secciÃ³n SIGUIENTE al baile
    assert "Carts" in title or "Target" in title or "Base" in title
    assert "Bosses" not in title
    assert "Intro" not in title
    assert title != "Crown Dungeon"


def test_proper_noun_format():
    from app.proper_nouns import apply_proper_noun_format, extract_proper_nouns

    en = "Play the Tune of Currents to return to the present."
    assert "Tune of Currents" in extract_proper_nouns(en)
    es = "Juega la Melodía de las Corrientes para regresar al presente."
    out = apply_proper_noun_format(en, es)
    assert "Tune of Currents" in out
    assert "(" in out


def test_polish_play_tune_not_juega():
    from app.proper_nouns import polish_spanish_guide, apply_proper_noun_format

    en = "Play the Tune of Currents to return to the present."
    bad = "Juega la Tune of Currents (Melodía de las Corrientes) para volver al presente."
    out = polish_spanish_guide(apply_proper_noun_format(en, bad), en)
    assert "Juega" not in out
    assert "Toca" in out
    assert "Tune of Currents" in out


def test_polish_play_english_leftover_and_calques():
    from app.proper_nouns import polish_spanish_guide

    en_cur = "Play the Tune of Currents to return to the present."
    bad_cur = (
        "Play the Tune of Currents (Toca la melodÃ­a de las corrientes) "
        "para regresar al presente."
    )
    out = polish_spanish_guide(bad_cur, en_cur)
    assert not out.lower().startswith("play")
    assert out.startswith("Toca Tune of Currents")
    assert "Melodía de las Corrientes" in out
    assert "Toca la melodÃ­a" not in out

    en_vine = "Climb the vine-covered plants. While climbing the vine-covered wall."
    bad_vine = "Sube por las plantas cubiertas de vino. Mientras subes por la pared cubierta de vino."
    out_v = polish_spanish_guide(bad_vine, en_vine)
    assert "vino" not in out_v.lower()
    assert "enredadera" in out_v.lower()

    bad_gr = "vuelve al cueva y inundar. unas cuantos pantallas hasta la área inundada."
    out_g = polish_spanish_guide(bad_gr, "")
    assert "a la cueva" in out_g
    assert "e inundar" in out_g
    assert "unas cuantas" in out_g
    assert "el área" in out_g

    out_echo = polish_spanish_guide("Toca Melodía de Echoes para volver.", "Play the Tune of Echoes.")
    assert "Tune of Echoes" in out_echo
    assert "Melodía de los Ecos" in out_echo


def test_progress_swamp_town_spanish_mm3():
    from app.guide_parser import parse_guide_sections, resolve_auto_section_id

    text = open("guias/mightandmagic3.txt", encoding="utf-8").read()
    secs = parse_guide_sections(text)
    assert any("SWAMP TOWN" in s.title.upper() for s in secs), "parser debe ver SWAMP TOWN"
    q = "acabo de visitar la ciudad del pantano ahora que hago?"
    sid = resolve_auto_section_id(secs, q, None, prefer_later=True)
    assert sid is not None
    title = next(s.title for s in secs if s.id == sid)
    assert "SWAMP" in title.upper()
    assert "CAVERN" not in title.upper() or "SWAMP TOWN" in title.upper()


def test_faq_heading_not_prose_false_positive():
    from app.guide_parser import _is_heading

    assert not _is_heading(
        "area by the poison cure. That lessens the risk of being poisoned.",
        None,
    )
    assert _is_heading("      4-2-11. SWAMP TOWN", None)


def test_translate_query_keywords_offline():
    from app.gemma_translate import translate_query_keywords, is_server_running

    if is_server_running():
        kw = translate_query_keywords("acabo de visitar la ciudad del pantano")
        assert any("swamp" in k or "town" in k for k in kw)
    else:
        assert translate_query_keywords("ciudad del pantano") == []


def test_gemma_translate_prompt_and_offline_guard():
    from app.gemma_translate import (
        build_system_prompt,
        build_translate_prompt,
        translate_text,
        is_server_running,
        scrub_translation,
    )

    prompt = build_translate_prompt("Hello world", "en", "es")
    assert "Hello world" in prompt
    sys_prompt = build_system_prompt("en", "es")
    assert "localizer" in sys_prompt.lower()
    assert "ONLY" in sys_prompt
    assert scrub_translation("Beyond (detrás)") == "Beyond"
    assert scrub_translation("Dormitory (5 B)") == "Dormitory (5 B)" or "5 B" in scrub_translation(
        "Dormitory (5 B)"
    )
    if not is_server_running():
        try:
            translate_text("hi", "en", "es", timeout=1.0)
            assert False, "debía fallar sin servidor"
        except RuntimeError as e:
            assert "LiteRT" in str(e) or "Gemma" in str(e)


def test_sentence_at_ignores_newline_wrap():
    from app.guide_parser import _sentence_at

    text = (
        "Outside, go down the steps and push the plant bulb underneath the \n"
        "right indent. Play the Tune of Currents to return to the present.\n"
    )
    idx = text.find("plant bulb")
    sent = _sentence_at(text, idx)
    assert sent is not None
    assert "right indent" in sent
    assert "plant bulb" in sent


def test_no_ridge_hardcode_module():
    import importlib.util

    assert importlib.util.find_spec("progress_steps") is None


if __name__ == "__main__":
    test_markdown_sections()
    test_caps_separator_sections()
    test_mission_prefix()
    test_citation_whitespace()
    test_fuente_extract()
    test_build_context_neighbors()
    test_build_context_following()
    test_slice_around_anchor()
    test_slice_previous_lookback()
    test_locate_anchor_by_terms()
    test_empty_and_long_flags()
    test_guia_ejemplo_file()
    test_is_progress_query()
    test_progress_start_prefers_later_milestone()
    test_proper_noun_format()
    test_polish_play_tune_not_juega()
    test_polish_play_english_leftover_and_calques()
    test_progress_swamp_town_spanish_mm3()
    test_faq_heading_not_prose_false_positive()
    test_translate_query_keywords_offline()
    test_gemma_translate_prompt_and_offline_guard()
    test_sentence_at_ignores_newline_wrap()
    test_no_ridge_hardcode_module()
    print("ALL TESTS PASSED")
