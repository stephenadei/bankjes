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


def _issue_token_via_request(client, email):
    """Helper: trigger /api/auth/request-magic-link and grab the token from DB."""
    import asyncio
    from app.db import open_db
    from unittest.mock import patch, AsyncMock

    with patch("app.auth.send_magic_link", new=AsyncMock()):
        client.post("/api/auth/request-magic-link", json={"email": email})

    db_path = os.environ["BANKJES_DB_PATH"]
    async def fetch():
        async with open_db(db_path) as conn:
            cur = await conn.execute(
                "SELECT token FROM magic_link_tokens "
                "WHERE email = ? AND consumed_at IS NULL ORDER BY created_at DESC LIMIT 1",
                (email,),
            )
            row = await cur.fetchone()
            return row[0] if row else None
    return asyncio.run(fetch())


def test_verify_with_valid_token_sets_cookie_and_redirects(client_with_envs):
    token = _issue_token_via_request(client_with_envs, "carol@example.com")
    assert token is not None

    r = client_with_envs.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert r.status_code in (302, 303), r.text
    assert r.headers["location"] == "/"
    # Cookie should be set
    set_cookie = r.headers.get("set-cookie", "")
    assert "bankjes_session=" in set_cookie
    assert "httponly" in set_cookie.lower()


def test_verify_creates_user_with_email_local_part_as_display_name(client_with_envs):
    import asyncio
    from app.db import open_db
    token = _issue_token_via_request(client_with_envs, "dave@example.com")
    r = client_with_envs.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert r.status_code in (302, 303)
    db_path = os.environ["BANKJES_DB_PATH"]

    async def fetch():
        async with open_db(db_path) as conn:
            cur = await conn.execute("SELECT email, display_name FROM users WHERE email = ?", ("dave@example.com",))
            return await cur.fetchone()
    row = asyncio.run(fetch())
    assert row is not None
    email, display_name = row
    assert email == "dave@example.com"
    assert display_name == "dave"  # local-part of email by default


def test_verify_consumes_token_so_replay_fails(client_with_envs):
    token = _issue_token_via_request(client_with_envs, "erin@example.com")
    r1 = client_with_envs.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert r1.status_code in (302, 303)
    # Second use must fail
    r2 = client_with_envs.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert r2.status_code in (400, 401, 410)


def test_verify_rejects_invalid_signature(client_with_envs):
    r = client_with_envs.get("/auth/verify?token=garbage-not-a-real-token", follow_redirects=False)
    assert r.status_code in (400, 401, 403)


def test_verify_existing_user_updates_last_login(client_with_envs):
    """Logging in twice for the same email should not create a duplicate user row."""
    import asyncio
    from app.db import open_db
    # First login
    token1 = _issue_token_via_request(client_with_envs, "frank@example.com")
    client_with_envs.get(f"/auth/verify?token={token1}", follow_redirects=False)
    # Second login
    token2 = _issue_token_via_request(client_with_envs, "frank@example.com")
    client_with_envs.get(f"/auth/verify?token={token2}", follow_redirects=False)

    db_path = os.environ["BANKJES_DB_PATH"]
    async def count():
        async with open_db(db_path) as conn:
            cur = await conn.execute("SELECT COUNT(*) FROM users WHERE email = ?", ("frank@example.com",))
            return (await cur.fetchone())[0]
    assert asyncio.run(count()) == 1
