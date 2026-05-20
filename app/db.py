"""SQLite connection + migration runner for the social-layer DB."""

from __future__ import annotations

import contextlib
from pathlib import Path

import aiosqlite

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


@contextlib.asynccontextmanager
async def open_db(path: str):
    """Open a SQLite connection with our standard pragmas."""
    async with aiosqlite.connect(path) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA foreign_keys=ON")
        yield conn


async def run_migrations(conn: aiosqlite.Connection) -> None:
    """Apply any unapplied 0NNN_*.sql migrations in lexical order.

    Tracks applied filenames in a schema_migrations table; safe to call
    repeatedly (idempotent — already-applied migrations are skipped).
    """
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  name TEXT PRIMARY KEY, applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    cur = await conn.execute("SELECT name FROM schema_migrations")
    applied = {row[0] for row in await cur.fetchall()}
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        sql = path.read_text()
        await conn.executescript(sql)
        await conn.execute(
            "INSERT INTO schema_migrations (name) VALUES (?)", (path.name,)
        )
        await conn.commit()
