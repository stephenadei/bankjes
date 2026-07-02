"""Own navigation — /api/route proxy + app.routing normalizer.

Hermetic like tests/test_endpoints.py: app.state.client is swapped for an
httpx.MockTransport client, ORS_API_KEY comes from monkeypatch, and the
route cache + daily budget are reset per test. No real ORS calls.
"""

import httpx
import pytest
from fastapi import HTTPException

from app import routing
from app.main import app, route, route_cache

# Minimal-but-real ORS directions/geojson shape (2 steps, 3 coords).
ORS_FIXTURE = {
    "features": [
        {
            "geometry": {
                # ORS speaks [lon, lat]
                "coordinates": [[4.90, 52.37], [4.905, 52.372], [4.91, 52.374]],
            },
            "properties": {
                "summary": {"distance": 850.3, "duration": 612.8},
                "segments": [
                    {
                        "steps": [
                            {
                                "instruction": "Ga rechtdoor op de Herengracht",
                                "distance": 500.0,
                                "duration": 360.0,
                                "type": 11,
                                "way_points": [0, 1],
                            },
                            {
                                "instruction": "U bent gearriveerd",
                                "distance": 350.3,
                                "duration": 252.8,
                                "type": 10,
                                "way_points": [1, 2],
                            },
                        ]
                    }
                ],
            },
        }
    ]
}


@pytest.fixture(autouse=True)
def _reset():
    route_cache.clear()
    routing._budget_day = None
    routing._budget_used = 0
    yield


def _mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ─── normalizer ────────────────────────────────────────────────────


def test_normalize_flips_coords_and_carries_steps():
    out = routing.normalize(ORS_FIXTURE)
    # [lon, lat] → [lat, lon]
    assert out["geometry"][0] == [52.37, 4.90]
    assert out["distance_m"] == 850
    assert out["duration_s"] == 613
    assert len(out["steps"]) == 2
    step = out["steps"][0]
    assert step["instruction"].startswith("Ga rechtdoor")
    assert step["geometry_idx"] == 0
    assert step["maneuver_point"] == [52.37, 4.90]
    # arrival step anchors at its own waypoint
    assert out["steps"][1]["geometry_idx"] == 1


def test_normalize_rejects_malformed():
    with pytest.raises(ValueError):
        routing.normalize({"features": []})


# ─── guards ────────────────────────────────────────────────────────


def test_service_area():
    assert routing.coords_in_service_area(52.37, 4.90)  # Amsterdam
    assert not routing.coords_in_service_area(48.85, 2.35)  # Parijs


def test_budget_caps_daily_calls():
    routing._budget_day = None
    routing._budget_used = 0
    assert routing.budget_allows()
    routing._budget_used = routing.DAILY_BUDGET
    assert not routing.budget_allows()


# ─── endpoint ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_route_happy_path(monkeypatch):
    monkeypatch.setenv("ORS_API_KEY", "test-key")

    def handler(req):
        assert "foot-walking" in str(req.url)
        assert req.headers["Authorization"] == "test-key"
        return httpx.Response(200, json=ORS_FIXTURE)

    async with _mock_client(handler) as client:
        app.state.client = client
        out = await route(from_lat=52.37, from_lon=4.90, to_lat=52.374, to_lon=4.91, mode="foot")

    assert out["distance_m"] == 850
    assert out["steps"][0]["maneuver_point"] == [52.37, 4.90]


@pytest.mark.asyncio
async def test_route_wheelchair_profile(monkeypatch):
    """The accessible mode must hit ORS's wheelchair profile — the reason
    ORS was chosen (see docs/specs/2026-07-02-own-navigation-design.md)."""
    monkeypatch.setenv("ORS_API_KEY", "test-key")
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        return httpx.Response(200, json=ORS_FIXTURE)

    async with _mock_client(handler) as client:
        app.state.client = client
        await route(from_lat=52.37, from_lon=4.90, to_lat=52.374, to_lon=4.91, mode="wheelchair")

    assert "/wheelchair/" in seen["url"]


@pytest.mark.asyncio
async def test_route_without_key_is_503(monkeypatch):
    monkeypatch.delenv("ORS_API_KEY", raising=False)
    with pytest.raises(HTTPException) as e:
        await route(from_lat=52.37, from_lon=4.90, to_lat=52.374, to_lon=4.91, mode="foot")
    assert e.value.status_code == 503


@pytest.mark.asyncio
async def test_route_outside_service_area_is_400(monkeypatch):
    monkeypatch.setenv("ORS_API_KEY", "test-key")
    with pytest.raises(HTTPException) as e:
        await route(from_lat=48.85, from_lon=2.35, to_lat=52.37, to_lon=4.90, mode="foot")
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_route_upstream_error_is_503_and_not_cached(monkeypatch):
    monkeypatch.setenv("ORS_API_KEY", "test-key")

    def handler(req):
        return httpx.Response(500, text="boom")

    async with _mock_client(handler) as client:
        app.state.client = client
        with pytest.raises(HTTPException) as e:
            await route(from_lat=52.37, from_lon=4.90, to_lat=52.374, to_lon=4.91, mode="foot")

    assert e.value.status_code == 503
    assert len(route_cache) == 0  # failure never pinned for the TTL


@pytest.mark.asyncio
async def test_route_budget_exhausted_is_429(monkeypatch):
    monkeypatch.setenv("ORS_API_KEY", "test-key")
    routing._budget_day = None
    routing._budget_used = 0
    routing.budget_allows()  # spend…
    routing._budget_used = routing.DAILY_BUDGET  # …and exhaust
    with pytest.raises(HTTPException) as e:
        await route(from_lat=52.37, from_lon=4.90, to_lat=52.374, to_lon=4.91, mode="foot")
    assert e.value.status_code == 429


@pytest.mark.asyncio
async def test_route_cache_hit_skips_budget_and_upstream(monkeypatch):
    monkeypatch.setenv("ORS_API_KEY", "test-key")
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json=ORS_FIXTURE)

    async with _mock_client(handler) as client:
        app.state.client = client
        await route(from_lat=52.37, from_lon=4.90, to_lat=52.374, to_lon=4.91, mode="foot")
        routing._budget_used = routing.DAILY_BUDGET  # exhausted after first call
        out = await route(from_lat=52.37, from_lon=4.90, to_lat=52.374, to_lon=4.91, mode="foot")

    assert calls["n"] == 1  # second answer came from cache
    assert out["distance_m"] == 850
