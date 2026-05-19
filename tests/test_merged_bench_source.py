"""Integration tests for MergedBenchSource via httpx.MockTransport."""

import httpx
import pytest

from app.sources import DsoSource, OsmSource, MergedBenchSource


@pytest.mark.asyncio
async def test_merged_combines_bgt_and_osm():
    """Composite returns BGT + OSM markers, deduplicated."""

    def handler(req: httpx.Request) -> httpx.Response:
        if "data.amsterdam.nl" in str(req.url):
            return httpx.Response(200, json={
                "features": [{
                    "id": "bgt-1",
                    "geometry": {"type": "Point", "coordinates": [4.90, 52.37]},
                    "properties": {"plusType": "bank"},
                }],
                "_links": [],
            })
        if "overpass-api.de" in str(req.url):
            return httpx.Response(200, json={
                "elements": [
                    # Far from bgt-1 — should survive
                    {"type": "node", "id": 1001, "lat": 52.40, "lon": 4.95, "tags": {"amenity": "bench"}},
                    # Within 10m of bgt-1 — should be dropped
                    {"type": "node", "id": 1002, "lat": 52.37, "lon": 4.9001, "tags": {"amenity": "bench"}},
                ],
            })
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        bgt = DsoSource(label="bgt-test", name="BGT-test", color="#000", path="bgt/straatmeubilair", params={"plusType": "bank"})
        osm = OsmSource(label="osm-test", name="OSM-test", color="#000", overpass_query='[out:json];node["amenity"="bench"]({s},{w},{n},{e});out;')
        merged = MergedBenchSource(bgt=bgt, osm=osm, dedup_m=10)
        out = await merged.fetch(client)

    ids = {m.id for m in out}
    assert "bgt-1" in ids
    assert "osm:1001" in ids
    assert "osm:1002" not in ids
    # bgt-1 should record the replica
    bgt1 = next(m for m in out if m.id == "bgt-1")
    assert bgt1.props.get("merged_replicas") == 1


def test_merged_source_protocol_fields():
    """Composite must satisfy the DataSource Protocol fields."""
    merged = MergedBenchSource(
        bgt=DsoSource(label="x", name="X", color="#000", path="p"),
        osm=OsmSource(label="y", name="Y", color="#000", overpass_query="q"),
    )
    assert merged.label == "bench"
    assert merged.name == "Banken"
    assert merged.source_type == "merged"
    assert merged.default_on is True
    assert merged.featured is True
