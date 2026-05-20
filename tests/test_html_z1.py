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


def test_new_spot_modal_present():
    html = _read("index.html")
    assert 'id="z1-new-spot-modal"' in html
    # Form fields by id
    assert 'id="z1-spot-label"' in html
    assert 'id="z1-spot-description"' in html
    assert 'id="z1-spot-category"' in html
    # Visibility-radio
    assert 'name="z1-visibility"' in html or 'id="z1-spot-visibility-private"' in html
    # Save button
    assert 'id="z1-spot-save"' in html


def test_new_spot_mini_map_present():
    html = _read("index.html")
    # Container for the small leaflet preview inside the modal
    assert 'id="z1-mini-map"' in html


def test_new_spot_categories_match_backend():
    """Frontend select must offer the same categories the backend accepts."""
    html = _read("index.html")
    for cat in ("bank", "stoel", "picknicktafel", "krukje", "anders"):
        assert f'value="{cat}"' in html, f"missing category {cat}"


def test_spots_layer_initialised():
    html = _read("index.html")
    # Frontend creates a dedicated cluster group for spots
    assert "z1RefreshSpots" in html
    assert "/api/spots" in html


def test_spot_popup_has_owner_actions_template():
    """The popup builder needs to render owner-specific buttons (request-public / delete)."""
    html = _read("index.html")
    # Strings used in the owner-action labels
    assert "Verzoek publicatie" in html or "request-public" in html.lower()
    assert "Verwijder" in html or "DELETE" in html


def test_mijn_plekjes_tab_present():
    html = _read("index.html")
    assert 'id="sheet-tab-nearby"' in html
    assert 'id="sheet-tab-mijn"' in html
    assert 'id="mijn-list"' in html


def test_mijn_plekjes_renderer_present():
    html = _read("index.html")
    assert "renderMijn" in html
