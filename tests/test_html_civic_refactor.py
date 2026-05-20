"""Asserts the HTML hooks for the civic-tech refactor are present."""

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"


def _read(name: str) -> str:
    return (STATIC_DIR / name).read_text()


def test_nearby_sheet_present():
    html = _read("index.html")
    assert 'id="nearby-sheet"' in html
    assert 'id="nearby-list"' in html
    assert 'class="nearby-handle"' in html


def test_nearby_list_has_lazy_renderer():
    html = _read("index.html")
    # The renderer references the items state and distance computation
    assert "function renderNearby" in html or "renderNearby(" in html
    assert "navigator.geolocation" in html  # geolocate fallback path exists


def test_mobile_bottom_bar_styling():
    html = _read("index.html")
    # Sentinel comment marks the new mobile-layout rules
    assert "/* bottom-bar mobile */" in html
    # Bottom-bar pinning of filters on mobile
    assert "bottom: 42px" in html or "bottom:42px" in html


def test_rugleun_filter_present():
    html = _read("index.html")
    assert 'id="rugleun-filter"' in html
    assert "localStorage" in html  # persistence
