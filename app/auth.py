"""Magic-link auth flow: request, verify, session-cookie helpers.

This module exposes a FastAPI router with the auth endpoints. Token
signing uses itsdangerous with the SECRET_KEY env var. Side-effects
(DB insert, Resend call) are isolated so the router stays testable.
"""

from __future__ import annotations

import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, EmailStr, ValidationError

from app.mail import send_magic_link

router = APIRouter()

MAGIC_LINK_TTL_SECONDS = 30 * 60   # 30 minutes
SESSION_TTL_SECONDS = 30 * 24 * 3600   # 30 days
SESSION_COOKIE_NAME = "bankjes_session"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MagicLinkRequest(BaseModel):
    email: str


def _serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY env var is required for auth")
    return URLSafeTimedSerializer(secret, salt="magic-link")


def _session_serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY env var is required for auth")
    return URLSafeTimedSerializer(secret, salt="session")


def _issue_session_cookie(response, user_id: str) -> None:
    """Sign + set the session cookie on the given response."""
    payload = {"user_id": user_id, "issued_at": _now_utc().isoformat()}
    token = _session_serializer().dumps(payload)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=True,
        path="/",
    )


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/api/auth/request-magic-link")
async def request_magic_link(payload: MagicLinkRequest, request: Request):
    email = payload.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="invalid email")

    db = request.app.state.db
    now = _now_utc()
    expires = now + timedelta(seconds=MAGIC_LINK_TTL_SECONDS)

    # Supersede any currently-active token for this email
    await db.execute(
        "UPDATE magic_link_tokens SET consumed_at = ? "
        "WHERE email = ? AND consumed_at IS NULL",
        (now.isoformat(), email),
    )

    nonce = secrets.token_urlsafe(8)
    token = _serializer().dumps({"email": email, "nonce": nonce})

    await db.execute(
        "INSERT INTO magic_link_tokens (token, email, expires_at) VALUES (?, ?, ?)",
        (token, email, expires.isoformat()),
    )
    await db.commit()

    base = os.environ.get("APP_BASE_URL", "").rstrip("/")
    link = f"{base}/auth/verify?token={token}"
    await send_magic_link(request.app.state.client, email, link)

    return {"sent": True}


@router.get("/auth/verify")
async def verify_magic_link(request: Request, token: str):
    db = request.app.state.db

    # Verify signature + age
    try:
        payload = _serializer().loads(token, max_age=MAGIC_LINK_TTL_SECONDS)
    except SignatureExpired:
        raise HTTPException(status_code=410, detail="link expired")
    except BadSignature:
        raise HTTPException(status_code=400, detail="invalid token")

    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="malformed token")

    # Verify DB row exists + not yet consumed
    cur = await db.execute(
        "SELECT email, consumed_at, expires_at FROM magic_link_tokens WHERE token = ?",
        (token,),
    )
    row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=400, detail="unknown token")
    db_email, consumed_at, expires_at = row
    if consumed_at is not None:
        raise HTTPException(status_code=410, detail="link already used")

    # Consume the token
    await db.execute(
        "UPDATE magic_link_tokens SET consumed_at = ? WHERE token = ?",
        (_now_utc().isoformat(), token),
    )

    # Upsert user
    cur = await db.execute("SELECT id FROM users WHERE email = ?", (email,))
    user_row = await cur.fetchone()
    if user_row is None:
        user_id = str(uuid.uuid4())
        display_name = email.split("@")[0]
        await db.execute(
            "INSERT INTO users (id, email, display_name, last_login_at) VALUES (?, ?, ?, ?)",
            (user_id, email, display_name, _now_utc().isoformat()),
        )
    else:
        user_id = user_row[0]
        await db.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (_now_utc().isoformat(), user_id),
        )

    await db.commit()

    response = RedirectResponse(url="/", status_code=302)
    _issue_session_cookie(response, user_id)
    return response
