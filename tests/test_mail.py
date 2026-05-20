"""Tests for app.mail.send_magic_link — Resend HTTP API wrapper."""

import os

import httpx
import pytest

from app.mail import send_magic_link


@pytest.mark.asyncio
async def test_send_magic_link_calls_resend_with_bearer_and_json(monkeypatch):
    """send_magic_link posts to Resend's /emails endpoint with Bearer auth + JSON body."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_DOMAIN", "mail.example.com")
    monkeypatch.setenv("MAIL_FROM", "Bankjes <login@mail.example.com>")

    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["method"] = req.method
        captured["auth"] = req.headers.get("authorization")
        captured["content-type"] = req.headers.get("content-type")
        captured["body"] = req.content.decode()
        return httpx.Response(200, json={"id": "abc-123"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await send_magic_link(client, "paul@example.com", "https://app.example/auth/verify?token=xyz")

    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["auth"] == "Bearer re_test_key"
    assert "application/json" in captured["content-type"]
    body = captured["body"]
    assert "paul@example.com" in body
    assert "https://app.example/auth/verify?token=xyz" in body
    assert "Bankjes <login@mail.example.com>" in body


@pytest.mark.asyncio
async def test_send_magic_link_uses_default_sender_when_mail_from_unset(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_DOMAIN", "mail.example.com")
    monkeypatch.delenv("MAIL_FROM", raising=False)

    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = req.content.decode()
        return httpx.Response(200, json={"id": "abc"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await send_magic_link(client, "paul@example.com", "https://x/y")

    # Default sender derived from RESEND_FROM_DOMAIN
    assert "Bankjes <login@mail.example.com>" in captured["body"]


@pytest.mark.asyncio
async def test_send_magic_link_raises_on_resend_error(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_DOMAIN", "mail.example.com")

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "domain not verified"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await send_magic_link(client, "paul@example.com", "https://x")
