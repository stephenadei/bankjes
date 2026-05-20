"""Asserts the head meta tags and visible asset references on the static pages."""

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"


def _read(name: str) -> str:
    return (STATIC_DIR / name).read_text()


def test_index_has_favicons():
    html = _read("index.html")
    assert 'rel="icon" type="image/svg+xml" href="/static/favicon.svg"' in html
    assert 'rel="apple-touch-icon" href="/static/apple-touch-icon.png"' in html


def test_index_has_og_meta():
    html = _read("index.html")
    assert 'property="og:image"' in html
    assert "og-banner.png" in html
    assert 'name="twitter:card" content="summary_large_image"' in html


def test_onderzoek_has_favicons_and_og():
    html = _read("onderzoek.html")
    assert "favicon.svg" in html
    assert "og-banner.png" in html


def test_header_mark_is_image():
    html = _read("index.html")
    # Old emoji should be gone from the hero
    assert '<span class="mark">🪑</span>' not in html
    # New image is in
    assert 'class="mark"' in html
    assert 'src="/static/silhouette.svg"' in html


def test_footer_about_card():
    html = _read("index.html")
    assert 'class="about"' in html
    assert "portrait-halftone.png" in html
    assert "Stephen Adei" in html
