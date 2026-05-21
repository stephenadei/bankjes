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


def test_index_has_redesign_header():
    html = _read("index.html")
    # Redesigned header uses bj-mark and bj-tabs
    assert 'class="bj-mark"' in html
    assert 'class="bj-tabs"' in html
    # Old Z v1 emoji mark should be gone
    assert '<span class="mark">🪑</span>' not in html


def test_index_has_bankjes_css():
    html = _read("index.html")
    assert "bankjes.css" in html


def test_index_has_filter_row():
    html = _read("index.html")
    assert 'id="bj-filter-row"' in html


def test_index_has_sidebar_and_sheet():
    html = _read("index.html")
    assert 'class="bj-sidebar"' in html or 'id="bj-sidebar"' in html
    assert 'class="bj-sheet' in html


def test_index_has_login_affordance():
    html = _read("index.html")
    assert "Inloggen" in html
    assert "/api/auth/request-magic-link" in html


def test_index_no_z1_fab():
    html = _read("index.html")
    assert 'id="z1-fab"' not in html
    assert 'id="z1-new-spot-modal"' not in html
