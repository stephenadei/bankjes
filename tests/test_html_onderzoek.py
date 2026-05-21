"""Shape tests for the redesigned onderzoek.html.

Checks that the file:
- contains the dual SVG density map anchors (#bgt-map, #osm-map)
- has the oversized H1 structure with .ond-h1 class
- does NOT query the defunct bench_osm dataset
- links bankjes.css (shared stylesheet)
- uses a single /api/items?dataset=bench fetch for map data
"""
import pathlib


ONDERZOEK = pathlib.Path(__file__).parent.parent / "app" / "static" / "onderzoek.html"


def _html() -> str:
    return ONDERZOEK.read_text(encoding="utf-8")


def test_file_exists():
    assert ONDERZOEK.exists(), "onderzoek.html not found"


def test_no_bench_osm_query():
    html = _html()
    assert "bench_osm" not in html, (
        "onderzoek.html must not reference the defunct bench_osm dataset"
    )


def test_has_bgt_map_div():
    assert 'id="bgt-map"' in _html(), "SVG with id=bgt-map not found"


def test_has_osm_map_div():
    assert 'id="osm-map"' in _html(), "SVG with id=osm-map not found"


def test_has_ond_h1():
    assert 'class="ond-h1"' in _html(), ".ond-h1 headline not found"


def test_links_bankjes_css():
    assert "bankjes.css" in _html(), "bankjes.css link not found"


def test_single_bench_fetch():
    """Map data must come from a single /api/items?dataset=bench fetch,
    not from two separate calls."""
    html = _html()
    # Only one occurrence of this fetch path expected
    count = html.count("/api/items?dataset=bench")
    assert count >= 1, "Expected at least one /api/items?dataset=bench fetch"
    assert "dataset=bench_osm" not in html, "bench_osm must not appear in fetch paths"


def test_splits_by_source_type():
    """JS must split items by props.source_type, not by dataset name."""
    html = _html()
    assert "source_type" in html, (
        "onderzoek.html must split markers by props.source_type"
    )
