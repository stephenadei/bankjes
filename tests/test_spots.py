"""Tests for app.spots — read-only listing with ACL."""

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("BANKJES_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-spots-only")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_FROM_DOMAIN", "mail.example.com")
    monkeypatch.setenv("APP_BASE_URL", "https://test.example")
    monkeypatch.setenv("BANKJES_INSECURE_COOKIES", "1")
    from app.main import app
    with TestClient(app) as c:
        yield c


def _seed_user(db_path, email):
    """Insert a user directly via aiosqlite, return their id."""
    from app.db import open_db
    async def go():
        async with open_db(db_path) as conn:
            uid = str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO users (id, email, display_name) VALUES (?, ?, ?)",
                (uid, email, email.split("@")[0]),
            )
            await conn.commit()
            return uid
    return asyncio.run(go())


def _seed_spot(db_path, owner_id, lat, lon, label,
               visibility="private", public_status="none"):
    from app.db import open_db
    async def go():
        async with open_db(db_path) as conn:
            sid = str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO spots (id, owner_id, lat, lon, label, visibility, public_status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sid, owner_id, lat, lon, label, visibility, public_status),
            )
            await conn.commit()
            return sid
    return asyncio.run(go())


def _login_as(client, email):
    from unittest.mock import patch, AsyncMock
    from app.db import open_db
    with patch("app.auth.send_magic_link", new=AsyncMock()):
        client.post("/api/auth/request-magic-link", json={"email": email})
    db_path = os.environ["BANKJES_DB_PATH"]
    async def fetch_token():
        async with open_db(db_path) as conn:
            cur = await conn.execute(
                "SELECT token FROM magic_link_tokens WHERE email = ? AND consumed_at IS NULL "
                "ORDER BY created_at DESC LIMIT 1",
                (email,),
            )
            row = await cur.fetchone()
            return row[0] if row else None
    token = asyncio.run(fetch_token())
    r = client.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_get_spots_anonymous_only_sees_public_approved(client):
    db = os.environ["BANKJES_DB_PATH"]
    owner = _seed_user(db, "owner@example.com")
    _seed_spot(db, owner, 52.37, 4.90, "private spot")  # private, none
    _seed_spot(db, owner, 52.38, 4.91, "pending pub",
               visibility="public", public_status="requested")
    _seed_spot(db, owner, 52.39, 4.92, "approved",
               visibility="public", public_status="approved")

    r = client.get("/api/spots")
    assert r.status_code == 200
    spots = r.json()["spots"]
    labels = sorted([s["label"] for s in spots])
    assert labels == ["approved"], f"got {labels}"


def test_get_spots_logged_in_sees_own_plus_public(client):
    db = os.environ["BANKJES_DB_PATH"]
    other = _seed_user(db, "other@example.com")
    _seed_spot(db, other, 52.37, 4.90, "other-private")
    _seed_spot(db, other, 52.39, 4.92, "other-approved",
               visibility="public", public_status="approved")

    _login_as(client, "me@example.com")
    # Get our user id via /api/me
    me_id = client.get("/api/me").json()["id"]
    _seed_spot(db, me_id, 52.40, 4.93, "my-private")

    r = client.get("/api/spots")
    assert r.status_code == 200
    labels = sorted([s["label"] for s in r.json()["spots"]])
    # other-private is invisible; other-approved is visible; my-private is mine
    assert labels == ["my-private", "other-approved"], f"got {labels}"


def test_get_spots_response_shape(client):
    db = os.environ["BANKJES_DB_PATH"]
    owner = _seed_user(db, "shape@example.com")
    _seed_spot(db, owner, 52.37, 4.90, "test", "public", "approved")

    r = client.get("/api/spots")
    assert r.status_code == 200
    spot = r.json()["spots"][0]
    for field in ("id", "lat", "lon", "label", "visibility", "public_status"):
        assert field in spot, f"missing field: {field}"
    assert "owner" in spot
    assert spot["owner"]["display_name"] == "shape"


def test_create_spot_requires_auth(client):
    r = client.post("/api/spots", json={"lat": 52.37, "lon": 4.90, "label": "x"})
    assert r.status_code == 401


def test_create_spot_minimal_payload(client):
    _login_as(client, "ivan@example.com")
    r = client.post("/api/spots", json={"lat": 52.37, "lon": 4.90, "label": "Mijn stoel"})
    assert r.status_code == 200, r.text
    spot = r.json()
    assert spot["lat"] == 52.37
    assert spot["lon"] == 4.90
    assert spot["label"] == "Mijn stoel"
    assert spot["visibility"] == "private"
    assert spot["public_status"] == "none"
    assert spot["category"] == "anders"
    assert "id" in spot
    assert spot["owner"]["display_name"] == "ivan"


def test_create_spot_with_all_optional_fields(client):
    _login_as(client, "jenny@example.com")
    payload = {
        "lat": 52.37,
        "lon": 4.90,
        "label": "Klapstoel",
        "description": "Voor de deur",
        "category": "stoel",
    }
    r = client.post("/api/spots", json=payload)
    assert r.status_code == 200
    spot = r.json()
    assert spot["description"] == "Voor de deur"
    assert spot["category"] == "stoel"


def test_create_spot_label_required(client):
    _login_as(client, "kara@example.com")
    r = client.post("/api/spots", json={"lat": 52.37, "lon": 4.90})
    assert r.status_code in (400, 422)


def test_create_spot_validates_lat_lon_ranges(client):
    _login_as(client, "leo@example.com")
    r = client.post("/api/spots", json={"lat": 999, "lon": 4.90, "label": "x"})
    assert r.status_code in (400, 422)
    r = client.post("/api/spots", json={"lat": 52.37, "lon": -999, "label": "x"})
    assert r.status_code in (400, 422)


def test_create_spot_rejects_overlong_label(client):
    _login_as(client, "mia@example.com")
    r = client.post("/api/spots", json={
        "lat": 52.37, "lon": 4.90, "label": "x" * 200,
    })
    assert r.status_code in (400, 422)


def test_create_spot_rejects_unknown_category(client):
    _login_as(client, "ned@example.com")
    r = client.post("/api/spots", json={
        "lat": 52.37, "lon": 4.90, "label": "ok", "category": "spaceship",
    })
    assert r.status_code in (400, 422)


def test_get_by_id_anonymous_404_on_private(client):
    db = os.environ["BANKJES_DB_PATH"]
    owner = _seed_user(db, "olga@example.com")
    sid = _seed_spot(db, owner, 52.37, 4.90, "private")
    r = client.get(f"/api/spots/{sid}")
    assert r.status_code == 404


def test_get_by_id_anonymous_sees_public_approved(client):
    db = os.environ["BANKJES_DB_PATH"]
    owner = _seed_user(db, "paco@example.com")
    sid = _seed_spot(db, owner, 52.37, 4.90, "approved", "public", "approved")
    r = client.get(f"/api/spots/{sid}")
    assert r.status_code == 200
    assert r.json()["label"] == "approved"


def test_get_by_id_owner_sees_own_private(client):
    _login_as(client, "quentin@example.com")
    me_id = client.get("/api/me").json()["id"]
    db = os.environ["BANKJES_DB_PATH"]
    sid = _seed_spot(db, me_id, 52.37, 4.90, "private")
    r = client.get(f"/api/spots/{sid}")
    assert r.status_code == 200
    assert r.json()["label"] == "private"


def test_patch_requires_owner(client):
    db = os.environ["BANKJES_DB_PATH"]
    other = _seed_user(db, "other-patch@example.com")
    sid = _seed_spot(db, other, 52.37, 4.90, "other's spot", "public", "approved")
    _login_as(client, "non-owner@example.com")
    r = client.patch(f"/api/spots/{sid}", json={"label": "hacked"})
    assert r.status_code == 403


def test_patch_owner_can_edit_label_desc_category(client):
    _login_as(client, "rita@example.com")
    me_id = client.get("/api/me").json()["id"]
    db = os.environ["BANKJES_DB_PATH"]
    sid = _seed_spot(db, me_id, 52.37, 4.90, "v1")
    r = client.patch(f"/api/spots/{sid}", json={
        "label": "v2", "description": "added", "category": "stoel",
    })
    assert r.status_code == 200
    spot = r.json()
    assert spot["label"] == "v2"
    assert spot["description"] == "added"
    assert spot["category"] == "stoel"


def test_patch_cannot_change_visibility(client):
    """Visibility transitions go through the dedicated request-public endpoints."""
    _login_as(client, "sven@example.com")
    me_id = client.get("/api/me").json()["id"]
    db = os.environ["BANKJES_DB_PATH"]
    sid = _seed_spot(db, me_id, 52.37, 4.90, "x")
    r = client.patch(f"/api/spots/{sid}", json={"visibility": "public"})
    # Either silently ignored or 4xx — both acceptable but field should not have changed
    spot = client.get(f"/api/spots/{sid}").json()
    assert spot["visibility"] == "private"


def test_delete_owner(client):
    _login_as(client, "tina@example.com")
    me_id = client.get("/api/me").json()["id"]
    db = os.environ["BANKJES_DB_PATH"]
    sid = _seed_spot(db, me_id, 52.37, 4.90, "doomed")
    r = client.delete(f"/api/spots/{sid}")
    assert r.status_code == 200
    # Confirm gone
    assert client.get(f"/api/spots/{sid}").status_code == 404


def test_delete_admin_can_delete_any(client, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    db = os.environ["BANKJES_DB_PATH"]
    other = _seed_user(db, "victim@example.com")
    sid = _seed_spot(db, other, 52.37, 4.90, "anyone")
    _login_as(client, "admin@example.com")
    r = client.delete(f"/api/spots/{sid}")
    assert r.status_code == 200


def test_delete_non_owner_403(client):
    db = os.environ["BANKJES_DB_PATH"]
    other = _seed_user(db, "vault@example.com")
    sid = _seed_spot(db, other, 52.37, 4.90, "their spot")
    _login_as(client, "intruder@example.com")
    r = client.delete(f"/api/spots/{sid}")
    assert r.status_code == 403


def test_request_public_owner_transitions_to_requested(client):
    _login_as(client, "ulla@example.com")
    me_id = client.get("/api/me").json()["id"]
    db = os.environ["BANKJES_DB_PATH"]
    sid = _seed_spot(db, me_id, 52.37, 4.90, "going public")

    with patch("app.spots._tg_notify_request") as ping:
        r = client.post(f"/api/spots/{sid}/request-public")

    assert r.status_code == 200
    spot = r.json()
    assert spot["visibility"] == "public"
    assert spot["public_status"] == "requested"
    ping.assert_called_once()


def test_request_public_non_owner_403(client):
    db = os.environ["BANKJES_DB_PATH"]
    other = _seed_user(db, "viola@example.com")
    sid = _seed_spot(db, other, 52.37, 4.90, "theirs")
    _login_as(client, "wim@example.com")
    with patch("app.spots._tg_notify_request"):
        r = client.post(f"/api/spots/{sid}/request-public")
    assert r.status_code == 403


def test_revoke_public_owner(client):
    _login_as(client, "xenia@example.com")
    me_id = client.get("/api/me").json()["id"]
    db = os.environ["BANKJES_DB_PATH"]
    sid = _seed_spot(db, me_id, 52.37, 4.90, "to revoke",
                     "public", "approved")
    r = client.post(f"/api/spots/{sid}/revoke-public")
    assert r.status_code == 200
    spot = r.json()
    assert spot["public_status"] == "revoked"


def test_revoke_public_returns_visibility_private(client):
    """After revoke, the spot becomes private to its owner."""
    _login_as(client, "yara@example.com")
    me_id = client.get("/api/me").json()["id"]
    db = os.environ["BANKJES_DB_PATH"]
    sid = _seed_spot(db, me_id, 52.37, 4.90, "downgrade",
                     "public", "approved")
    client.post(f"/api/spots/{sid}/revoke-public")
    spot = client.get(f"/api/spots/{sid}").json()
    assert spot["visibility"] == "private"


def test_request_public_resubmit_after_denial(client):
    """After denied, an owner can request again."""
    _login_as(client, "zane@example.com")
    me_id = client.get("/api/me").json()["id"]
    db = os.environ["BANKJES_DB_PATH"]
    # Seed as previously denied
    async def seed():
        from app.db import open_db
        async with open_db(os.environ["BANKJES_DB_PATH"]) as conn:
            sid = str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO spots (id, owner_id, lat, lon, label, "
                "visibility, public_status, denial_reason) "
                "VALUES (?, ?, ?, ?, ?, 'private', 'denied', 'not yet')",
                (sid, me_id, 52.37, 4.90, "retry"),
            )
            await conn.commit()
            return sid
    sid = asyncio.run(seed())
    with patch("app.spots._tg_notify_request"):
        r = client.post(f"/api/spots/{sid}/request-public")
    assert r.status_code == 200
    assert r.json()["public_status"] == "requested"
