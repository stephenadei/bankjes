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
