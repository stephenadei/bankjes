"""Assertions on the static HTML for the Z v1 social-layer UI."""

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"


def _read(name: str) -> str:
    return (STATIC_DIR / name).read_text()


def test_fab_present():
    html = _read("index.html")
    assert 'id="z1-fab"' in html
    # Big plus glyph or aria-label
    assert 'aria-label="Voeg plekje toe"' in html or "voeg-plekje" in html


def test_login_modal_present():
    html = _read("index.html")
    assert 'id="z1-login-modal"' in html
    # Email input
    assert 'name="email"' in html or 'id="z1-login-email"' in html
    # Submit button text
    assert "magic-link" in html.lower() or "stuur link" in html.lower()


def test_fab_click_handler_wired():
    html = _read("index.html")
    # The JS handler should call /api/me before deciding which modal to open
    assert "/api/me" in html
    assert "z1-fab" in html
