import os
import tempfile

from app.guide_importer import (
    MIN_GUIDE_CHARS,
    GuideImportError,
    GuideImporter,
    detect_adapter,
    discover_eliteguias_chapters,
    extract_gamefaqs_text,
    html_to_text,
    is_eliteguias_chapter_url,
    safe_slug,
    unique_guide_path,
    validate_http_url,
)


def test_validate_http_url_ok():
    assert validate_http_url(" https://example.com/a ").startswith("https://")


def test_validate_http_url_rejects_ftp():
    try:
        validate_http_url("ftp://x")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_safe_slug_strips_weird():
    s = safe_slug("Final Fantasy VI!!!")
    assert " " not in s
    assert s.lower().startswith("final")


def test_unique_guide_path_collision():
    with tempfile.TemporaryDirectory() as d:
        p1 = unique_guide_path(d, "ff6")
        open(p1, "w", encoding="utf-8").write("x" * (MIN_GUIDE_CHARS + 1))
        p2 = unique_guide_path(d, "ff6")
        assert p1 != p2
        assert p2.endswith(".txt")


def test_html_to_text_strips_script():
    html = "<html><script>bad()</script><p>Hola guia</p></html>"
    t = html_to_text(html)
    assert "bad" not in t
    assert "Hola" in t


def test_discover_eliteguias_chapters_sorted():
    html = open("fixtures/eliteguias_hub_sample.html", encoding="utf-8").read()
    hub = "https://www.eliteguias.com/guias/f/ff6/final-fantasy-vi.php"
    urls = discover_eliteguias_chapters(hub, html)
    assert [u.split("-p")[-1] for u in urls] == ["1.php", "2.php", "10.php"]
    assert all(u.startswith("https://www.eliteguias.com/") for u in urls)


def test_is_eliteguias_chapter_url():
    assert is_eliteguias_chapter_url(
        "https://www.eliteguias.com/guias/f/ff6/final-fantasy-vi-p3.php"
    )
    assert not is_eliteguias_chapter_url(
        "https://www.eliteguias.com/guias/f/ff6/final-fantasy-vi.php"
    )


def test_extract_gamefaqs_prefers_pre():
    html = open("fixtures/gamefaqs_pre_sample.html", encoding="utf-8").read()
    t = extract_gamefaqs_text(html)
    assert "Go east to the village" in t
    assert "menu" not in t.lower() or "Go east" in t


def test_detect_adapter():
    assert (
        detect_adapter("https://www.eliteguias.com/guias/f/ff6/final-fantasy-vi.php")
        == "eliteguias"
    )
    assert (
        detect_adapter("https://gamefaqs.gamespot.com/gbc/472313-x/faqs/36108")
        == "gamefaqs"
    )
    assert detect_adapter("https://example.com/guide") == "generic"


class FakeImporter(GuideImporter):
    def __init__(self, mapping, guides_dir):
        super().__init__(guides_dir=guides_dir)
        self.mapping = mapping

    def fetch(self, url: str):
        if url not in self.mapping:
            raise GuideImportError(f"missing fixture url {url}")
        status, body = self.mapping[url]
        if status in (401, 403, 429):
            raise GuideImportError(
                "El sitio bloqueÃ³ la descarga (HTTP %s). "
                "GuardÃ¡ el texto a mano o usÃ¡ Cargar .txt." % status
            )
        if status >= 400:
            raise GuideImportError(f"Error HTTP {status}")
        return url, body


def test_import_eliteguias_hub_writes_file():
    hub = "https://www.eliteguias.com/guias/f/ff6/final-fantasy-vi.php"
    hub_html = open("fixtures/eliteguias_hub_sample.html", encoding="utf-8").read()
    mapping = {
        hub: (200, hub_html),
        "https://www.eliteguias.com/guias/f/ff6/final-fantasy-vi-p1.php": (
            200,
            "<html><title>P1</title><body><p>" + ("paso uno " * 80) + "</p></body></html>",
        ),
        "https://www.eliteguias.com/guias/f/ff6/final-fantasy-vi-p2.php": (
            200,
            "<html><title>P2</title><body><p>" + ("paso dos " * 80) + "</p></body></html>",
        ),
        "https://www.eliteguias.com/guias/f/ff6/final-fantasy-vi-p10.php": (
            200,
            "<html><title>P10</title><body><p>" + ("paso diez " * 80) + "</p></body></html>",
        ),
    }
    with tempfile.TemporaryDirectory() as d:
        imp = FakeImporter(mapping, d)
        import app.guide_importer as gi

        old = gi.CHAPTER_PAUSE_SEC
        gi.CHAPTER_PAUSE_SEC = 0
        try:
            result = imp.import_url(hub)
        finally:
            gi.CHAPTER_PAUSE_SEC = old
        assert result.pages == 3
        assert result.chars >= MIN_GUIDE_CHARS
        assert os.path.exists(result.path)
        text = open(result.path, encoding="utf-8").read()
        assert "##" in text


def test_import_403():
    url = "https://gamefaqs.gamespot.com/gbc/x/faqs/1"
    with tempfile.TemporaryDirectory() as d:
        imp = FakeImporter({url: (403, "")}, d)
        try:
            imp.import_url(url)
            assert False
        except GuideImportError as e:
            assert "bloqueÃ³" in str(e).lower() or "403" in str(e)


if __name__ == "__main__":
    test_validate_http_url_ok()
    test_validate_http_url_rejects_ftp()
    test_safe_slug_strips_weird()
    test_unique_guide_path_collision()
    test_html_to_text_strips_script()
    test_discover_eliteguias_chapters_sorted()
    test_is_eliteguias_chapter_url()
    test_extract_gamefaqs_prefers_pre()
    test_detect_adapter()
    test_import_eliteguias_hub_writes_file()
    test_import_403()
    print("ALL TESTS PASSED")
