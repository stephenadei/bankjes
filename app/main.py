"""Stephen's Bankjes — Amsterdam Street Furniture Explorer.

Pure-proxy FastAPI backend. All fetching, caching, and source-specific
logic lives in app.sources. This file is just orchestration: routing,
caching, and shaping the response.
"""

import asyncio
import logging
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
