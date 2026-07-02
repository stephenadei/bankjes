"""Asserts the in-app navigation hooks are present — and Google Maps gone.

Style mirrors tests/test_html_civic_refactor.py: string asserts against the
static HTML the frontend tests pin.
"""

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"


def _read(name: str) -> str:
    return (STATIC_DIR / name).read_text()


def test_nav_container_and_module_present():
    html = _read("index.html")
    assert 'id="bj-nav"' in html
    assert "navStartPreview" in html
    assert "watchPosition" in html  # live turn-by-turn loop
    assert "/api/route" in html  # own backend, not an external router


def test_nav_has_all_three_modes():
    html = _read("index.html")
    for mode in ("foot", "bike", "wheelchair"):
        assert f'"{mode}"' in html or f"'{mode}'" in html


def test_google_maps_route_link_gone():
    """The 'Open in Maps' hand-off is replaced by in-app navigation. The
    Street View link stays until the Mapillary viewer (phase 2)."""
    html = _read("index.html")
    assert "google.com/maps/search" not in html
    assert 'id="bj-popup-route"' in html


def test_admin_uses_osm_not_google():
    html = _read("admin.html")
    assert "google.com/maps" not in html
    assert "openstreetmap.org" in html


def test_nav_degrades_without_backend():
    """No ORS key / ORS down → the card offers the open OSM-directions
    fallback instead of a dead end."""
    html = _read("index.html")
    assert "openstreetmap.org/directions" in html
