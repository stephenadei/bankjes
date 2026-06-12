"""Hermetic tests for the frontend-facing API: /api/items, /api/datasets, /api/photos.

These endpoints are the contract the map UI leans on; a response-shape
regression here ships straight to the browser (see #5). They are exercised
with an httpx.MockTransport client swapped onto app.state.client — no network,
so they run in CI. Mirrors the pattern in test_busyness.py.
"""

import httpx
import pytest
from fastapi import HTTPException

from app.main import (
    app,
    cache,
    datasets,
    items,
    photo_cache,
    photos,
)


def _mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _geojson(features):
    """A single-page DSO GeoJSON FeatureCollection (no rel=next link)."""
    return {"type": "FeatureCollection", "features": features, "_links": []}


def _point(mid, lat, lon, **props):
    return {
        "type": "Feature",
        "id": mid,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": props,
    }


# ─── /api/datasets ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_datasets_shape_and_source_types():
    out = await datasets()

    assert isinstance(out, list) and out
    by_label = {d["label"]: d for d in out}

    # Every dataset exposes the keys the frontend builds itself from.
    for d in out:
        assert set(d) >= {
            "label", "name", "color", "sourceType",
            "sourceTypes", "defaultOn", "featured",
        }

    # sourceTypes is the redesign array, derived from the single sourceType.
    assert by_label["bench"]["sourceType"] == "merged"
    assert by_label["bench"]["sourceTypes"] == ["BGT", "OSM"]
    assert by_label["picnic_table"]["sourceTypes"] == ["BGT"]      # dso
    assert by_label["laadpunten"]["sourceTypes"] == ["OSM"]        # osm


# ─── /api/items ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_items_shapes_each_marker_with_its_dataset():
    cache.clear()

    def handler(req):
        # picnic_table is a single-source DSO dataset → only DSO is hit.
        return httpx.Response(200, json=_geojson([
            _point("a", 52.36, 4.90, plusType="picknicktafel"),
            _point("b", 52.37, 4.91, plusType="picknicktafel"),
        ]))

    async with _mock_client(handler) as client:
        app.state.client = client
        out = await items(dataset="picnic_table", bbox=None)

    assert out["count"] == 2
    assert len(out["items"]) == 2
    for item in out["items"]:
        assert set(item) >= {"id", "lat", "lon", "props", "dataset"}
        assert item["dataset"] == "picnic_table"


@pytest.mark.asyncio
async def test_items_bbox_filters_out_markers_outside_the_box():
    cache.clear()

    def handler(req):
        return httpx.Response(200, json=_geojson([
            _point("inside", 52.35, 4.90),   # within the bbox below
            _point("outside", 10.00, 4.90),  # far south — excluded
        ]))

    async with _mock_client(handler) as client:
        app.state.client = client
        out = await items(dataset="picnic_table", bbox="52.30,4.80,52.40,4.95")

    assert out["count"] == 1
    assert out["items"][0]["id"] == "inside"


@pytest.mark.asyncio
async def test_items_rejects_unknown_dataset():
    # The guard runs before any fetch, so this needs no network.
    with pytest.raises(HTTPException) as exc:
        await items(dataset="does_not_exist", bbox=None)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_items_rejects_malformed_bbox():
    with pytest.raises(HTTPException) as exc:
        await items(dataset="picnic_table", bbox="not,a,bbox")
    assert exc.value.status_code == 400


# ─── /api/photos ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_photos_without_token_returns_empty(monkeypatch):
    photo_cache.clear()
    monkeypatch.setattr("app.main.MAPILLARY_TOKEN", None)

    out = await photos(lat=52.37, lon=4.90, radius=50, limit=3)

    assert out == {"photos": []}


@pytest.mark.asyncio
async def test_photos_parses_and_sorts_by_distance(monkeypatch):
    photo_cache.clear()
    monkeypatch.setattr("app.main.MAPILLARY_TOKEN", "test-token")

    def handler(req):
        return httpx.Response(200, json={"data": [
            # farther from the query point (4.90, 52.37)
            {"id": "far", "thumb_256_url": "t-far", "thumb_1024_url": "l-far",
             "captured_at": 2, "geometry": {"coordinates": [4.95, 52.40]}},
            # nearer — should sort first
            {"id": "near", "thumb_256_url": "t-near", "thumb_1024_url": "l-near",
             "captured_at": 1, "geometry": {"coordinates": [4.901, 52.371]}},
            # no thumbnail → dropped
            {"id": "nothumb", "geometry": {"coordinates": [4.90, 52.37]}},
        ]})

    async with _mock_client(handler) as client:
        app.state.client = client
        out = await photos(lat=52.37, lon=4.90, radius=50, limit=3)

    ids = [p["id"] for p in out["photos"]]
    assert ids == ["near", "far"]  # distance-sorted, no-thumb dropped
    near = out["photos"][0]
    assert set(near) >= {"id", "thumb", "large", "captured_at", "url"}
    assert near["thumb"] == "t-near"
    assert near["large"] == "l-near"
    assert "pKey=near" in near["url"]


@pytest.mark.asyncio
async def test_photos_degrades_on_upstream_error(monkeypatch):
    photo_cache.clear()
    monkeypatch.setattr("app.main.MAPILLARY_TOKEN", "test-token")

    def handler(req):
        raise httpx.ConnectError("mapillary unreachable")

    async with _mock_client(handler) as client:
        app.state.client = client
        out = await photos(lat=52.37, lon=4.90, radius=50, limit=3)

    assert out == {"photos": []}


@pytest.mark.asyncio
async def test_photos_degrades_on_non_200(monkeypatch):
    photo_cache.clear()
    monkeypatch.setattr("app.main.MAPILLARY_TOKEN", "test-token")

    def handler(req):
        return httpx.Response(429, text="rate limited")

    async with _mock_client(handler) as client:
        app.state.client = client
        out = await photos(lat=52.37, lon=4.90, radius=50, limit=3)

    assert out == {"photos": []}
