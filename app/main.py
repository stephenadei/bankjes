"""Stephen's Bankjes — Amsterdam Street Furniture Explorer.

Pure-proxy FastAPI backend. All fetching, caching, and source-specific
logic lives in app.sources. This file is just orchestration: routing,
caching, and shaping the response.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import httpx
from cachetools import TTLCache
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse

from app.domain import Bbox, Marker, MarkerWithSource
from app.sources import DATASETS, DATASETS_BY_LABEL, DataSource

# Benches don't move; an hour of staleness is fine and avoids
# making the first visitor after idle pay the Overpass cold cost.
CACHE_TTL_SECONDS = 3600

cache: TTLCache = TTLCache(maxsize=64, ttl=CACHE_TTL_SECONDS)
# Photo lookups dwarf dataset count; a day of staleness is fine.
photo_cache: TTLCache = TTLCache(maxsize=2000, ttl=86400)

MAPILLARY_TOKEN: Optional[str] = os.environ.get("MAPILLARY_TOKEN") or None

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=60.0)
    # Pre-warm the cache for datasets the UI loads on first paint,
    # so the first visitor sees warm timings instead of the ~2.4s
    # Overpass cold call.
    app.state.prewarm = asyncio.create_task(_prewarm(app.state.client))
    yield
    app.state.prewarm.cancel()
    await app.state.client.aclose()


async def _prewarm(client: httpx.AsyncClient) -> None:
    targets = [ds for ds in DATASETS if ds.default_on]
    for ds in targets:
        try:
            await _cached_fetch(ds, client)
            log.info("prewarm: %s loaded (%d cached)", ds.label, len(cache[ds.label]))
        except Exception as e:
            log.warning("prewarm: %s failed: %s", ds.label, e)


app = FastAPI(
    title="Stephen's Bankjes — Amsterdam Street Furniture",
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1024)

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/onderzoek", include_in_schema=False)
async def onderzoek():
    return FileResponse(STATIC_DIR / "onderzoek.html")


@app.get("/healthz")
async def healthz():
    return {"ok": True, "datasets": sorted(DATASETS_BY_LABEL.keys())}


@app.get("/api/datasets")
async def datasets():
    """Frontend's single source of truth for what to render. camelCase for JS."""
    return [
        {
            "label":      d.label,
            "name":       d.name,
            "color":      d.color,
            "sourceType": d.source_type,
            "defaultOn":  d.default_on,
            "featured":   d.featured,
        }
        for d in DATASETS
    ]


async def _cached_fetch(ds: DataSource, client: httpx.AsyncClient) -> list[Marker]:
    if ds.label in cache:
        return cache[ds.label]
    markers = await ds.fetch(client)
    cache[ds.label] = markers
    return markers


@app.get("/api/items")
async def items(
    dataset: Optional[str] = Query(
        default=None,
        description="One of: " + ", ".join(sorted(DATASETS_BY_LABEL.keys())),
    ),
    bbox: Optional[str] = Query(
        default=None,
        description="south,west,north,east in WGS84",
    ),
):
    if dataset is not None and dataset not in DATASETS_BY_LABEL:
        raise HTTPException(status_code=400, detail=f"Unknown dataset: {dataset}")

    bb: Optional[Bbox] = None
    if bbox:
        try:
            bb = Bbox.parse(bbox)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    targets: list[DataSource] = (
        [DATASETS_BY_LABEL[dataset]] if dataset else list(DATASETS)
    )

    results = await asyncio.gather(
        *[_cached_fetch(ds, app.state.client) for ds in targets]
    )

    out: list[MarkerWithSource] = []
    for ds, markers in zip(targets, results):
        for m in markers:
            if bb is not None and not bb.contains(m.lat, m.lon):
                continue
            out.append(MarkerWithSource(
                id=m.id, lat=m.lat, lon=m.lon, props=m.props,
                dataset=ds.label,
            ))

    return {"count": len(out), "items": [m.model_dump() for m in out]}


@app.get("/api/photos")
async def photos(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius: int = Query(default=25, ge=5, le=200, description="meters"),
    limit: int = Query(default=3, ge=1, le=10),
):
    """Nearby street-level photos via Mapillary. Empty list if no token or no coverage."""
    if not MAPILLARY_TOKEN:
        return {"photos": []}

    key = f"{lat:.5f},{lon:.5f},{radius},{limit}"
    if key in photo_cache:
        return photo_cache[key]

    delta = radius / 111000  # degrees per meter, good enough at NL latitudes
    bbox = f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"

    try:
        r = await app.state.client.get(
            "https://graph.mapillary.com/images",
            params={
                "access_token": MAPILLARY_TOKEN,
                "bbox": bbox,
                "limit": max(limit * 3, 10),
                "fields": "id,thumb_256_url,thumb_1024_url,captured_at,compass_angle,geometry",
            },
            timeout=10.0,
        )
    except httpx.HTTPError as e:
        log.warning("mapillary fetch failed: %s", e)
        return {"photos": []}

    if r.status_code != 200:
        log.warning("mapillary %d: %s", r.status_code, r.text[:200])
        return {"photos": []}

    raw = r.json().get("data", [])

    def dist_sq(img: dict) -> float:
        coords = (img.get("geometry") or {}).get("coordinates") or [0, 0]
        return (coords[0] - lon) ** 2 + (coords[1] - lat) ** 2

    raw.sort(key=dist_sq)

    out = [
        {
            "id": img["id"],
            "thumb": img.get("thumb_256_url"),
            "large": img.get("thumb_1024_url"),
            "captured_at": img.get("captured_at"),
            "url": f"https://www.mapillary.com/app/?focus=photo&pKey={img['id']}",
        }
        for img in raw[:limit]
        if img.get("thumb_256_url")
    ]

    result = {"photos": out}
    photo_cache[key] = result
    return result
