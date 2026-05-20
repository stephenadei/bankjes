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

from fastapi import APIRouter, HTTPException, Request
from itsdangerous import URLSafeTimedSerializer
from pydantic import BaseModel, EmailStr, ValidationError

from app.mail import send_magic_link

router = APIRouter()

MAGIC_LINK_TTL_SECONDS = 30 * 60   # 30 minutes
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MagicLinkRequest(BaseModel):
    email: str


def _serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY env var is required for auth")
    return URLSafeTimedSerializer(secret, salt="magic-link")


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
