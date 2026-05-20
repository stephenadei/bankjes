"""Resend HTTP API wrapper. One function: send_magic_link.

Reads RESEND_API_KEY + RESEND_FROM_DOMAIN at call time from env.
Raises httpx.HTTPStatusError on non-2xx responses (no silent fallbacks
— failure to send a magic link must surface).
"""

from __future__ import annotations

import os

import httpx


async def send_magic_link(client: httpx.AsyncClient, email: str, link: str) -> None:
    api_key = os.environ["RESEND_API_KEY"]
    domain = os.environ["RESEND_FROM_DOMAIN"]
    sender = os.environ.get("MAIL_FROM", f"Bankjes <login@{domain}>")
    body_text = (
        f"Hoi,\n\n"
        f"Klik deze link om in te loggen op Stephen's Bankjes:\n\n"
        f"{link}\n\n"
        f"Link verloopt over 30 minuten. Vraag je geen login aan, "
        f"negeer dit bericht — niemand kan zonder de link je account benaderen."
    )
    r = await client.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": sender,
            "to": [email],
            "subject": "Inloggen — Stephen's Bankjes",
            "text": body_text,
        },
        timeout=10.0,
    )
    r.raise_for_status()
