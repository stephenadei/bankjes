"""Asserts the HTML hooks for the redesigned civic-tech UI are present."""

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"


def _read(name: str) -> str:
    return (STATIC_DIR / name).read_text()


def test_nearby_sheet_present():
    html = _read("index.html")
    # Redesigned sheet uses bj-sheet class and bj-sheet-handle
    assert 'id="bj-sheet"' in html
    assert 'id="bj-sheet-list"' in html
    assert 'id="bj-sheet-handle"' in html


def test_nearby_list_has_lazy_renderer():
    html = _read("index.html")
    # The renderer references the items state and distance computation
    assert "renderNearbyList" in html or "renderNearby" in html
    assert "navigator.geolocation" in html  # geolocate fallback path exists


def test_mobile_bottom_bar_styling():
    html = _read("index.html")
    # Redesigned mobile sheet uses bj-sheet classes
    assert "bj-sheet-peek" in html
    assert "bj-sheet-half" in html or "bj-sheet-full" in html
    # Mobile filter row present
    assert "bj-filter-row-mobile" in html


def test_rugleun_filter_present():
    html = _read("index.html")
    # Redesigned rugleuning uses bj-mod + bj-rugleun ids
    assert "rugleuning" in html
    assert "localStorage" in html  # persistence
