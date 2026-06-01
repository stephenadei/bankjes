"""Tests for the /api/busyness neighbourhood-density proxy.

Hermetic: app.state.client is swapped for an httpx.MockTransport client, so
no real Overpass calls happen — these run in CI.
"""

import httpx
import pytest

from app.main import _busyness_level, app, busyness, busyness_cache


def test_busyness_level_thresholds():
    assert _busyness_level(0) == "rustig"
    assert _busyness_level(14) == "rustig"
    assert _busyness_level(15) == "gemiddeld"
    assert _busyness_level(49) == "gemiddeld"
    assert _busyness_level(50) == "druk"
    assert _busyness_level(500) == "druk"


def _mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_busyness_parses_overpass_count():
    busyness_cache.clear()

    def handler(req):
        # Overpass `out count;` response shape
        return httpx.Response(200, json={
            "elements": [{"type": "count", "id": 0, "tags": {"total": "63"}}],
        })

    async with _mock_client(handler) as client:
        app.state.client = client
        out = await busyness(lat=52.37, lon=4.90, radius=150)

    assert out["score"] == 63
    assert out["level"] == "druk"
    assert out["radius"] == 150


@pytest.mark.asyncio
async def test_busyness_sends_around_query():
    busyness_cache.clear()
    captured = {}

    def handler(req):
        captured["query"] = req.url.params.get("data")
        return httpx.Response(200, json={"elements": [{"type": "count", "tags": {"total": "5"}}]})

    async with _mock_client(handler) as client:
        app.state.client = client
        out = await busyness(lat=52.37, lon=4.90, radius=150)

    q = captured["query"]
    assert "around:150,52.37,4.9" in q
    assert "amenity" in q and "shop" in q and "public_transport" in q
    assert out["level"] == "rustig"  # 5 < 15


@pytest.mark.asyncio
async def test_busyness_degrades_on_upstream_error():
    busyness_cache.clear()

    def handler(req):
        return httpx.Response(503, text="overloaded")

    async with _mock_client(handler) as client:
        app.state.client = client
        out = await busyness(lat=52.37, lon=4.90, radius=150)

    assert out["score"] is None
    assert out["level"] is None
