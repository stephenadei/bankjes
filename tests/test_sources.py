"""Tests for DataSource adapters in app.sources.

Uses httpx.MockTransport to intercept at the transport layer — no real
network calls. Demonstrates the leverage from extracting DataSource as
a proper seam: every fetch path (pagination, header injection, query
interpolation, GeoJSON/Overpass decoding) is now testable in isolation.
"""

import httpx
import pytest

from app.sources import DATASETS, DATASETS_BY_LABEL, DsoSource, OsmSource


# ─── DsoSource ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dso_decodes_geojson_to_markers():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "features": [{
                "id": "feat-1",
                "geometry": {"type": "Point", "coordinates": [4.9, 52.37]},
                "properties": {"plusType": "bank", "color": "blauw"},
            }],
            "_links": [],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        src = DsoSource(label="t", name="T", color="#000", path="bgt/x")
        markers = await src.fetch(client)

    assert len(markers) == 1
    m = markers[0]
    assert m.id == "feat-1"
    assert m.lat == 52.37 and m.lon == 4.9
    assert m.props["color"] == "blauw"


@pytest.mark.asyncio
async def test_dso_follows_rel_next_pagination():
    seen_urls = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen_urls.append(str(req.url))
        if "page=2" in str(req.url):
            return httpx.Response(200, json={
                "features": [{
                    "id": "f2",
                    "geometry": {"type": "Point", "coordinates": [5.0, 52.4]},
                    "properties": {},
                }],
                "_links": [],
            })
        return httpx.Response(200, json={
            "features": [{
                "id": "f1",
                "geometry": {"type": "Point", "coordinates": [4.9, 52.37]},
                "properties": {},
            }],
            "_links": [{"rel": "next", "href": "https://api.data.amsterdam.nl/v1/bgt/x/?page=2"}],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        src = DsoSource(label="t", name="T", color="#000", path="bgt/x")
        markers = await src.fetch(client)

    assert {m.id for m in markers} == {"f1", "f2"}
    assert len(seen_urls) == 2
    assert "page=2" in seen_urls[1]


@pytest.mark.asyncio
async def test_dso_skips_non_point_geometries():
    def handler(req):
        return httpx.Response(200, json={
            "features": [
                {"id": "p", "geometry": {"type": "Point", "coordinates": [4.9, 52.37]}, "properties": {}},
                {"id": "poly", "geometry": {"type": "Polygon", "coordinates": []}, "properties": {}},
                {"id": "missing-geom", "geometry": None, "properties": {}},
            ],
            "_links": [],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        src = DsoSource(label="t", name="T", color="#000", path="bgt/x")
        markers = await src.fetch(client)

    assert [m.id for m in markers] == ["p"]


@pytest.mark.asyncio
async def test_dso_sends_x_api_key_header_when_set(monkeypatch):
    monkeypatch.setattr("app.sources.AMSTERDAM_API_KEY", "test-key-abc")
    captured = {}

    def handler(req):
        captured["key"] = req.headers.get("X-API-Key")
        return httpx.Response(200, json={"features": [], "_links": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        src = DsoSource(label="t", name="T", color="#000", path="bgt/x")
        await src.fetch(client)

    assert captured["key"] == "test-key-abc"


@pytest.mark.asyncio
async def test_dso_omits_header_when_no_key(monkeypatch):
    monkeypatch.setattr("app.sources.AMSTERDAM_API_KEY", None)
    captured = {}

    def handler(req):
        captured["key"] = req.headers.get("X-API-Key")
        return httpx.Response(200, json={"features": [], "_links": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        src = DsoSource(label="t", name="T", color="#000", path="bgt/x")
        await src.fetch(client)

    assert captured["key"] is None


# ─── OsmSource ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_osm_interpolates_bbox_into_query():
    captured = {}

    def handler(req):
        captured["query"] = req.url.params.get("data")
        return httpx.Response(200, json={"elements": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        src = OsmSource(
            label="t", name="T", color="#000",
            overpass_query='node["amenity"="bench"]({s},{w},{n},{e});out;',
        )
        await src.fetch(client)

    # AMSTERDAM = Bbox(52.295, 4.745, 52.430, 5.020)
    q = captured["query"]
    assert "52.295" in q and "4.745" in q
    assert "52.43" in q and "5.02" in q
    assert "amenity" in q


@pytest.mark.asyncio
async def test_osm_returns_markers_from_nodes_only():
    def handler(req):
        return httpx.Response(200, json={
            "elements": [
                {"type": "node", "id": 1, "lat": 52.37, "lon": 4.9, "tags": {"amenity": "bench"}},
                {"type": "way", "id": 2, "nodes": []},  # not a node, skip
                {"type": "node", "id": 3, "lat": 52.38, "lon": 4.91},  # no tags
                {"type": "node", "id": 4},  # no coords, skip
            ],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        src = OsmSource(
            label="t", name="T", color="#000",
            overpass_query='node["amenity"="bench"]({s},{w},{n},{e});out;',
        )
        markers = await src.fetch(client)

    assert {m.id for m in markers} == {"osm:1", "osm:3"}
    by_id = {m.id: m for m in markers}
    assert by_id["osm:1"].props == {"amenity": "bench"}
    assert by_id["osm:3"].props == {}


@pytest.mark.asyncio
async def test_osm_sends_user_agent():
    captured = {}

    def handler(req):
        captured["ua"] = req.headers.get("User-Agent")
        return httpx.Response(200, json={"elements": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        src = OsmSource(
            label="t", name="T", color="#000",
            overpass_query='node["amenity"="bench"]({s},{w},{n},{e});out;',
        )
        await src.fetch(client)

    assert captured["ua"] and "stephens-bankjes" in captured["ua"]


# ─── DATASETS registration ─────────────────────────────────────────

def test_datasets_have_unique_labels():
    labels = [d.label for d in DATASETS]
    assert len(labels) == len(set(labels)), "duplicate labels in DATASETS"
    assert set(DATASETS_BY_LABEL.keys()) == set(labels)


def test_datasets_carry_required_metadata():
    for d in DATASETS:
        assert d.label, f"{d} missing label"
        assert d.name, f"{d.label} missing name"
        assert d.color.startswith("#"), f"{d.label} color must be hex"
        assert d.source_type in ("dso", "osm")


def test_bench_dataset_uses_amsterdam_bronhouder():
    """If we ever drop the bronhouder filter, BGT data leaks neighbouring towns."""
    bench = DATASETS_BY_LABEL["bench"]
    assert isinstance(bench, DsoSource)
    assert bench.params.get("bronhouder") == "G0363"
