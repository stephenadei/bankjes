"""Hermetic tests for /api/photos after the cached-proxy-fetch rewire (#14).

app.state.client is swapped for an httpx.MockTransport client, so no real
Mapillary calls happen.
"""

import httpx

import app.main as main
from app.main import app, photo_cache, photos


def _mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_photos_shapes_and_caches(monkeypatch):
    photo_cache.clear()
    monkeypatch.setattr(main, "MAPILLARY_TOKEN", "tok")

    def handler(req):
        return httpx.Response(200, json={"data": [
            {"id": "abc", "thumb_256_url": "t256", "thumb_1024_url": "t1024",
             "captured_at": 1, "geometry": {"coordinates": [4.90, 52.37]}},
        ]})

    async with _mock_client(handler) as client:
        app.state.client = client
        out = await photos(lat=52.37, lon=4.90, radius=50, limit=3)

    assert out["photos"][0]["id"] == "abc"
    assert out["photos"][0]["thumb"] == "t256"
    assert out["photos"][0]["large"] == "t1024"
    assert "pKey=abc" in out["photos"][0]["url"]
    # success is cached
    assert photo_cache["52.37000,4.90000,50,3"] == out


async def test_photos_degrades_on_upstream_error(monkeypatch):
    photo_cache.clear()
    monkeypatch.setattr(main, "MAPILLARY_TOKEN", "tok")

    def handler(req):
        return httpx.Response(503, text="overloaded")

    async with _mock_client(handler) as client:
        app.state.client = client
        out = await photos(lat=52.37, lon=4.90, radius=50, limit=3)

    assert out == {"photos": []}
    # degraded result is NOT cached
    assert "52.37000,4.90000,50,3" not in photo_cache


async def test_photos_no_token_short_circuits(monkeypatch):
    monkeypatch.setattr(main, "MAPILLARY_TOKEN", None)
    out = await photos(lat=52.37, lon=4.90, radius=50, limit=3)
    assert out == {"photos": []}
