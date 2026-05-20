"""Tests for app.auth — magic-link request flow."""

import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_with_envs(monkeypatch, tmp_path):
    monkeypatch.setenv("BANKJES_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-tests-only")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_FROM_DOMAIN", "mail.example.com")
    monkeypatch.setenv("APP_BASE_URL", "https://test.example")
    from app.main import app
    with TestClient(app) as client:
        yield client


def test_request_magic_link_returns_sent(client_with_envs):
    with patch("app.auth.send_magic_link", new=AsyncMock()) as fake_send:
        r = client_with_envs.post(
            "/api/auth/request-magic-link",
            json={"email": "paul@example.com"},
        )
        assert r.status_code == 200
        assert r.json() == {"sent": True}
        fake_send.assert_awaited_once()
        # Second positional arg is the email
        called_email = fake_send.await_args.args[1]
        assert called_email == "paul@example.com"
        # Third arg is the URL with token query-param
        called_link = fake_send.await_args.args[2]
        assert called_link.startswith("https://test.example/auth/verify?token=")


def test_request_magic_link_inserts_token_row(client_with_envs):
    import asyncio
    from app.db import open_db
    with patch("app.auth.send_magic_link", new=AsyncMock()):
        r = client_with_envs.post(
            "/api/auth/request-magic-link",
            json={"email": "alice@example.com"},
        )
        assert r.status_code == 200
    # Inspect the DB
    db_path = os.environ["BANKJES_DB_PATH"]
    async def check():
        async with open_db(db_path) as conn:
            cur = await conn.execute(
                "SELECT email, consumed_at, expires_at FROM magic_link_tokens WHERE email = ?",
                ("alice@example.com",),
            )
            return await cur.fetchone()
    row = asyncio.run(check())
    assert row is not None
    email, consumed_at, expires_at = row
    assert email == "alice@example.com"
    assert consumed_at is None
    assert expires_at is not None


def test_request_magic_link_validates_email_shape(client_with_envs):
    with patch("app.auth.send_magic_link", new=AsyncMock()):
        # Missing @
        r = client_with_envs.post(
            "/api/auth/request-magic-link",
            json={"email": "not-an-email"},
        )
        assert r.status_code == 422 or r.status_code == 400


def test_request_magic_link_supersedes_active_token(client_with_envs):
    """Requesting twice for same email expires the first token."""
    import asyncio
    from app.db import open_db
    db_path = os.environ["BANKJES_DB_PATH"]
    with patch("app.auth.send_magic_link", new=AsyncMock()):
        client_with_envs.post("/api/auth/request-magic-link", json={"email": "bob@example.com"})
        client_with_envs.post("/api/auth/request-magic-link", json={"email": "bob@example.com"})

    async def check():
        async with open_db(db_path) as conn:
            cur = await conn.execute(
                "SELECT consumed_at FROM magic_link_tokens WHERE email = ? ORDER BY created_at",
                ("bob@example.com",),
            )
            return [row[0] for row in await cur.fetchall()]
    statuses = asyncio.run(check())
    # The first token should now be consumed (superseded); the second is open.
    assert len(statuses) == 2
    assert statuses[0] is not None   # superseded → consumed_at set
    assert statuses[1] is None       # active
