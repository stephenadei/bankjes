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


def test_google_gone_entirely():
    """Full de-Google: no google.* reference anywhere — the route hand-off
    became in-app nav, Street View became Mapillary (fase 2), fonts are
    self-hosted (fase 4)."""
    for page in ("index.html", "onderzoek.html", "admin.html", "coming-soon.html"):
        html = _read(page)
        assert "google" not in html.lower(), f"google reference left in {page}"


def test_street_view_is_mapillary_now():
    html = _read("index.html")
    assert "mapillary.com/app" in html
    assert 'id="bj-popup-route"' in html


def test_fonts_self_hosted():
    fonts_css = (STATIC_DIR / "fonts" / "fonts.css").read_text()
    assert "@font-face" in fonts_css
    assert "fonts.gstatic.com" not in fonts_css  # rewritten to local files
    for page in ("index.html", "onderzoek.html", "admin.html", "coming-soon.html"):
        assert "/static/fonts/fonts.css" in _read(page)
    woff2 = list((STATIC_DIR / "fonts").glob("*.woff2"))
    assert len(woff2) >= 3  # Fraunces (normal+italic) + Inter


def test_admin_uses_osm_not_google():
    html = _read("admin.html")
    assert "openstreetmap.org" in html


def test_route_engine_attribution_present():
    """Fair-use requirement of the keyless FOSSGIS fallback: the card names
    the engine + OSM data credit."""
    html = _read("index.html")
    assert "FOSSGIS" in html
    assert "OpenRouteService" in html


def test_nav_degrades_without_backend():
    """No ORS key / ORS down → the card offers the open OSM-directions
    fallback instead of a dead end."""
    html = _read("index.html")
    assert "openstreetmap.org/directions" in html
