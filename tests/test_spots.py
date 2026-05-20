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
