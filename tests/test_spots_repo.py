"""Unit tests for app.spots_repo — mapper + ACL in isolation.

These exercise the extracted SpotRepository helpers without spinning up
the FastAPI app or touching a DB, so the row-to-dict mapping and the
row-level ACL are verified directly against synthetic rows.
"""

from types import SimpleNamespace

from app.spots_repo import spot_row_to_dict, user_can_see


# Mirrors the SPOT_SELECT_COLUMNS projection (11 columns).
PUBLIC_ROW = (
    "spot-1", "owner-1", 52.37, 4.90, "Bankje", "bij de gracht",
    "bank", "public", "approved", "2026-06-01T10:00:00", "Stephen",
)

# Mirrors the ADMIN_SPOT_SELECT_COLUMNS projection (13 columns).
ADMIN_ROW = (
    "spot-2", "owner-2", 52.38, 4.91, "Stoel", "voor de deur",
    "stoel", "private", "denied", "te vaag",
    "2026-06-01T11:00:00", "Ivan", "ivan@example.com",
)


def test_public_mapper_shape():
    d = spot_row_to_dict(PUBLIC_ROW)
    assert d == {
        "id": "spot-1",
        "lat": 52.37,
        "lon": 4.90,
        "label": "Bankje",
        "description": "bij de gracht",
        "category": "bank",
        "visibility": "public",
        "public_status": "approved",
        "created_at": "2026-06-01T10:00:00",
        "owner": {"id": "owner-1", "display_name": "Stephen"},
    }
    # The public projection must not leak admin-only fields.
    assert "denial_reason" not in d
    assert "email" not in d["owner"]


def test_admin_mapper_shape():
    d = spot_row_to_dict(ADMIN_ROW, admin=True)
    assert d == {
        "id": "spot-2",
        "lat": 52.38,
        "lon": 4.91,
        "label": "Stoel",
        "description": "voor de deur",
        "category": "stoel",
        "visibility": "private",
        "public_status": "denied",
        "denial_reason": "te vaag",
        "created_at": "2026-06-01T11:00:00",
        "owner": {
            "id": "owner-2",
            "display_name": "Ivan",
            "email": "ivan@example.com",
        },
    }


def test_user_can_see_public_approved_for_anonymous():
    spot = spot_row_to_dict(PUBLIC_ROW)
    assert user_can_see(spot, None) is True


def test_user_can_see_hides_private_from_anonymous():
    private_row = (
        "s", "owner-x", 52.0, 4.0, "geheim", None,
        "anders", "private", "none", "2026-06-01T00:00:00", "X",
    )
    spot = spot_row_to_dict(private_row)
    assert user_can_see(spot, None) is False


def test_user_can_see_owner_sees_own_private():
    private_row = (
        "s", "owner-9", 52.0, 4.0, "mijn", None,
        "anders", "private", "none", "2026-06-01T00:00:00", "Me",
    )
    spot = spot_row_to_dict(private_row)
    owner = SimpleNamespace(id="owner-9")
    stranger = SimpleNamespace(id="someone-else")
    assert user_can_see(spot, owner) is True
    assert user_can_see(spot, stranger) is False
