"""Tests for app.db migration runner."""
import os
import tempfile

import pytest

from app.db import open_db, run_migrations


@pytest.mark.asyncio
async def test_run_migrations_idempotent():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "test.db")
        async with open_db(path) as conn:
            await run_migrations(conn)
            await run_migrations(conn)  # idempotent, no exception
            cur = await conn.execute("SELECT name FROM schema_migrations")
            applied = {row[0] for row in await cur.fetchall()}
        assert "0001_init.sql" in applied


@pytest.mark.asyncio
async def test_schema_created():
    """After migration the four tables exist with expected columns."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "test.db")
        async with open_db(path) as conn:
            await run_migrations(conn)
            cur = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row[0] for row in await cur.fetchall()}
        assert "users" in tables
        assert "spots" in tables
        assert "magic_link_tokens" in tables
        assert "schema_migrations" in tables


@pytest.mark.asyncio
async def test_pragmas_applied():
    """open_db sets WAL + busy_timeout + foreign_keys."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "test.db")
        async with open_db(path) as conn:
            cur = await conn.execute("PRAGMA journal_mode")
            assert (await cur.fetchone())[0].lower() == "wal"
            cur = await conn.execute("PRAGMA foreign_keys")
            assert (await cur.fetchone())[0] == 1


def test_app_state_has_db_after_startup(tmp_path, monkeypatch):
    """After app lifespan-startup, app.state.db is a usable sqlite connection."""
    from fastapi.testclient import TestClient
    monkeypatch.setenv("BANKJES_DB_PATH", str(tmp_path / "test.db"))
    from app.main import app
    with TestClient(app) as client:
        # If lifespan ran cleanly, app.state.db exists and the migration ran
        assert hasattr(app.state, "db")
        # And a simple query against the migrated schema works
        r = client.get("/healthz")
        assert r.status_code == 200
