"""Hermetic tests for the API surface the frontend depends on (#15).

The vanilla-JS frontend fetches /api/datasets for what to render and
/api/items for the Markers; marker popups call /api/photos. These tests
pin the response shapes those calls rely on.

Hermetic: app.state.client is swapped for an httpx.MockTransport client and
the module-level caches are cleared per test, so no real DSO/OSM/Mapillary
calls happen — they run in CI without network. Mirrors tests/test_sources.py
and tests/test_busyness.py.
"""

import httpx
import pytest

from app.main import app, cache, datasets, items, photos, photo_cache


def _mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ─── /api/items ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_items_each_item_carries_dataset_field():
    """The frontend groups markers by their `dataset` label; every item
    in the response must carry it."""
    cache.clear()

    def handler(req):
        # OsmSource hits Overpass and decodes `elements` nodes → Markers.
        return httpx.Response(200, json={
            "elements": [
                {"type": "node", "id": 1, "lat": 52.37, "lon": 4.90, "tags": {"amenity": "charging_station"}},
                {"type": "node", "id": 2, "lat": 52.38, "lon": 4.91, "tags": {}},
            ],
        })

    async with _mock_client(handler) as client:
        app.state.client = client
        out = await items(dataset="laadpunten", bbox=None)

    assert out["count"] == 2
    assert len(out["items"]) == 2
    for item in out["items"]:
        assert item["dataset"] == "laadpunten"


@pytest.mark.asyncio
async def test_items_bbox_filtering_narrows_results():
    """A bbox that contains only one of two markers must drop the other."""
    cache.clear()

    def handler(req):
        return httpx.Response(200, json={
            "elements": [
                # inside the tight bbox below
                {"type": "node", "id": 1, "lat": 52.370, "lon": 4.900, "tags": {}},
                # well outside it
                {"type": "node", "id": 2, "lat": 52.420, "lon": 5.000, "tags": {}},
            ],
        })

    # Without bbox: both markers come back.
    async with _mock_client(handler) as client:
        app.state.client = client
        unfiltered = await items(dataset="laadpunten", bbox=None)
    assert unfiltered["count"] == 2

    cache.clear()

    # With a bbox around only the first marker: just one survives.
    async with _mock_client(handler) as client:
        app.state.client = client
        filtered = await items(dataset="laadpunten", bbox="52.36,4.89,52.38,4.91")

    assert filtered["count"] == 1
    assert filtered["items"][0]["id"] == "osm:1"
    assert filtered["items"][0]["dataset"] == "laadpunten"


# ─── /api/datasets ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_datasets_response_shape():
    """The frontend reads label/name/sourceType/sourceTypes off each entry."""
    out = await datasets()

    assert isinstance(out, list) and out
    for d in out:
        assert isinstance(d["label"], str) and d["label"]
        assert isinstance(d["name"], str) and d["name"]
        assert d["sourceType"] in ("dso", "osm", "merged")
        assert isinstance(d["sourceTypes"], list) and d["sourceTypes"]
        assert all(st in ("BGT", "OSM") for st in d["sourceTypes"])


@pytest.mark.asyncio
async def test_datasets_merged_bench_exposes_both_source_types():
    """`bench` is the composite BGT+OSM source; its sourceTypes array must
    surface both registers so the redesign legend can split them."""
    out = await datasets()
    bench = next(d for d in out if d["label"] == "bench")
    assert bench["sourceType"] == "merged"
    assert bench["sourceTypes"] == ["BGT", "OSM"]


# ─── /api/photos ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_photos_empty_without_token(monkeypatch):
    """No MAPILLARY_TOKEN → graceful empty list, no upstream call."""
    monkeypatch.setattr("app.main.MAPILLARY_TOKEN", None)
    photo_cache.clear()

    out = await photos(lat=52.37, lon=4.90, radius=50, limit=3)

    assert out == {"photos": []}


@pytest.mark.asyncio
async def test_photos_degrades_on_upstream_error(monkeypatch):
    """Token present but Mapillary errors → still an empty list, not a 500."""
    monkeypatch.setattr("app.main.MAPILLARY_TOKEN", "fake-token")
    photo_cache.clear()

    def handler(req):
        return httpx.Response(500, text="mapillary down")

    async with _mock_client(handler) as client:
        app.state.client = client
        out = await photos(lat=52.37, lon=4.90, radius=50, limit=3)

    assert out == {"photos": []}
