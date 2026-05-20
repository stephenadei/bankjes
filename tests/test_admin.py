"""Tests for app.admin — public-register approve/deny/demote with dual auth."""

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("BANKJES_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SECRET_KEY", "test-admin-secret")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_FROM_DOMAIN", "mail.example.com")
    monkeypatch.setenv("APP_BASE_URL", "https://test.example")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_TOKEN", "secret-admin-token-xxx")
    monkeypatch.setenv("BANKJES_INSECURE_COOKIES", "1")
    from app.main import app
    with TestClient(app) as c:
        yield c


def _seed_user(db_path, email):
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


def _seed_requested_spot(db_path, owner_id, label="pending"):
    from app.db import open_db
    async def go():
        async with open_db(db_path) as conn:
            sid = str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO spots (id, owner_id, lat, lon, label, visibility, public_status) "
                "VALUES (?, ?, ?, ?, ?, 'public', 'requested')",
                (sid, owner_id, 52.37, 4.90, label),
            )
            await conn.commit()
            return sid
    return asyncio.run(go())


def _login_as(client, email):
    from app.db import open_db
    with patch("app.auth.send_magic_link", new=AsyncMock()):
        client.post("/api/auth/request-magic-link", json={"email": email})
    db_path = os.environ["BANKJES_DB_PATH"]
    async def fetch():
        async with open_db(db_path) as conn:
            cur = await conn.execute(
                "SELECT token FROM magic_link_tokens WHERE email = ? AND consumed_at IS NULL "
                "ORDER BY created_at DESC LIMIT 1",
                (email,),
            )
            row = await cur.fetchone()
            return row[0] if row else None
    token = asyncio.run(fetch())
    client.get(f"/auth/verify?token={token}", follow_redirects=False)


def test_admin_endpoints_403_for_non_admin_session(client):
    _login_as(client, "regular@example.com")
    r = client.get("/api/admin/spots/pending")
    assert r.status_code == 403


def test_admin_endpoints_401_for_anonymous(client):
    r = client.get("/api/admin/spots/pending")
    assert r.status_code == 401


def test_admin_via_session_email_works(client):
    db = os.environ["BANKJES_DB_PATH"]
    owner = _seed_user(db, "owner@example.com")
    _seed_requested_spot(db, owner)
    _login_as(client, "admin@example.com")
    r = client.get("/api/admin/spots/pending")
    assert r.status_code == 200
    assert len(r.json()["spots"]) == 1


def test_admin_via_token_header_works(client):
    db = os.environ["BANKJES_DB_PATH"]
    owner = _seed_user(db, "owner2@example.com")
    _seed_requested_spot(db, owner)
    r = client.get(
        "/api/admin/spots/pending",
        headers={"X-Admin-Token": "secret-admin-token-xxx"},
    )
    assert r.status_code == 200


def test_admin_wrong_token_403(client):
    r = client.get(
        "/api/admin/spots/pending",
        headers={"X-Admin-Token": "wrong"},
    )
    assert r.status_code in (401, 403)


def test_approve_transitions_to_approved(client):
    db = os.environ["BANKJES_DB_PATH"]
    owner = _seed_user(db, "owner-approve@example.com")
    sid = _seed_requested_spot(db, owner, "yes-please")
    hdrs = {"X-Admin-Token": "secret-admin-token-xxx"}
    r = client.post(f"/api/admin/spots/{sid}/approve", headers=hdrs, json={})
    assert r.status_code == 200, r.text
    # Reflected
    r2 = client.get(f"/api/spots/{sid}")
    assert r2.json()["public_status"] == "approved"


def test_deny_requires_reason_minlen(client):
    db = os.environ["BANKJES_DB_PATH"]
    owner = _seed_user(db, "owner-deny@example.com")
    sid = _seed_requested_spot(db, owner)
    hdrs = {"X-Admin-Token": "secret-admin-token-xxx"}

    # Empty reason → fail
    r = client.post(f"/api/admin/spots/{sid}/deny", headers=hdrs, json={"reason": "x"})
    assert r.status_code in (400, 422)

    # Valid reason → ok
    r = client.post(
        f"/api/admin/spots/{sid}/deny",
        headers=hdrs,
        json={"reason": "Past niet bij civic-tech catalogus"},
    )
    assert r.status_code == 200


def test_demote_approved_spot_to_revoked(client):
    """Stephen's safety-net for spots that become problematic after approval."""
    db = os.environ["BANKJES_DB_PATH"]
    owner_email = "owner-demote@example.com"
    owner = _seed_user(db, owner_email)
    # Seed as approved
    from app.db import open_db
    async def seed():
        async with open_db(db) as conn:
            sid = str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO spots (id, owner_id, lat, lon, label, visibility, public_status) "
                "VALUES (?, ?, ?, ?, ?, 'public', 'approved')",
                (sid, owner, 52.37, 4.90, "approved-to-demote"),
            )
            await conn.commit()
            return sid
    sid = asyncio.run(seed())
    hdrs = {"X-Admin-Token": "secret-admin-token-xxx"}
    r = client.post(
        f"/api/admin/spots/{sid}/demote",
        headers=hdrs,
        json={"reason": "Klachten ontvangen over content"},
    )
    assert r.status_code == 200
    # Login as owner to see their demoted spot
    _login_as(client, owner_email)
    r2 = client.get(f"/api/spots/{sid}")
    assert r2.status_code == 200
    assert r2.json()["public_status"] == "revoked"
