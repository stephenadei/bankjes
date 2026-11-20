"""A degraded bench merge must not be pinned in the hour-long items cache.

Prd served count=345 (BGT only) for up to an hour after an Overpass blip:
_cached_fetch cached the half-merge like a full one. It may be kept briefly
(degraded_cache, 60 s) but the next fetch after that must return the full merge.
"""

import httpx
import pytest

from app.main import (
    DEGRADED_CACHE_TTL_SECONDS,
    app,
    cache,
    degraded_cache,
    items,
)
from app.sources import OVERPASS_URL


def _handler(state):
    def handler(req):
        if str(req.url).startswith(OVERPASS_URL):
            if state["overpass_down"]:
                return httpx.Response(504)
            # 52.39 is far from the BGT bench, so dedup keeps both.
            return httpx.Response(200, json={"elements": [
                {"type": "node", "id": 7, "lat": 52.39, "lon": 4.95, "tags": {"amenity": "bench"}},
            ]})
        return httpx.Response(200, json={"type": "FeatureCollection", "_links": [], "features": [
            {"type": "Feature", "id": "bgt-1", "geometry": {"type": "Point", "coordinates": [4.90, 52.37]},
             "properties": {"plusType": "bank"}},
        ]})
    return handler


@pytest.mark.asyncio
async def test_degraded_merge_not_cached_for_the_hour():
    cache.clear()
    degraded_cache.clear()
    state = {"overpass_down": True}
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler(state))) as client:
        app.state.client = client

        degraded = await items(dataset="bench", bbox=None)
        assert degraded["count"] == 1                      # BGT only
        assert "bench" not in cache                        # not pinned for the hour
        assert "bench" in degraded_cache
        assert DEGRADED_CACHE_TTL_SECONDS <= 60

        # Overpass recovers; once the short TTL lapses the full merge comes back.
        state["overpass_down"] = False
        degraded_cache.clear()                             # = 60 s later
        full = await items(dataset="bench", bbox=None)
        assert full["count"] == 2
        assert {i["props"]["source_type"] for i in full["items"]} == {"bgt", "osm"}
        assert "bench" in cache                            # a full merge is cached normally

