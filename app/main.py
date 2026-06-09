"""Stephen's Bankjes — Amsterdam Street Furniture Explorer.

Pure-proxy FastAPI backend. All fetching, caching, and source-specific
logic lives in app.sources. This file is just orchestration: routing,
caching, and shaping the response.
"""

import asyncio
import contextlib
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
from fastapi.staticfiles import StaticFiles

from app.admin import router as admin_router
from app.auth import router as auth_router
from app.db import open_db, run_migrations
from app.domain import Bbox, Marker, MarkerWithSource
from app.proxy_cache import cached_proxy_fetch
from app.sources import DATASETS, DATASETS_BY_LABEL, DataSource, OVERPASS_URL
from app.spots import router as spots_router

# Benches don't move; an hour of staleness is fine and avoids
# making the first visitor after idle pay the Overpass cold cost.
CACHE_TTL_SECONDS = 3600

cache: TTLCache = TTLCache(maxsize=64, ttl=CACHE_TTL_SECONDS)
# Photo lookups dwarf dataset count; a day of staleness is fine.
photo_cache: TTLCache = TTLCache(maxsize=2000, ttl=86400)
# Neighbourhood-busyness proxy (nearby POI density); a day of staleness is fine.
busyness_cache: TTLCache = TTLCache(maxsize=2000, ttl=86400)

MAPILLARY_TOKEN: Optional[str] = os.environ.get("MAPILLARY_TOKEN") or None

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with contextlib.AsyncExitStack() as stack:
        app.state.client = httpx.AsyncClient(timeout=60.0)
        stack.push_async_callback(app.state.client.aclose)

        db_path = os.environ.get("BANKJES_DB_PATH", "/data/bankjes.db")
        # Ensure parent dir exists (so tests with tmp_path work and prod /data is created if missing)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        app.state.db = await stack.enter_async_context(open_db(db_path))
        await run_migrations(app.state.db)

        # Pre-warm the cache for datasets the UI loads on first paint,
        # so the first visitor sees warm timings instead of the ~2.4s
        # Overpass cold call.
        app.state.prewarm = asyncio.create_task(_prewarm(app.state.client))
        try:
            yield
        finally:
            app.state.prewarm.cancel()


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
app.include_router(auth_router)
app.include_router(spots_router)
app.include_router(admin_router)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _should_serve_coming_soon(preview: Optional[str]) -> bool:
    """On prd the public surfaces (/, /onderzoek) are gated behind a
    coming-soon page so the site can sit live without being open to traffic.
    ?preview=soon forces the page on pre/acc for copy review."""
    if preview == "soon":
        return True
    return os.environ.get("APP_ENV", "").lower() == "prd"


@app.get("/", include_in_schema=False)
async def index(preview: Optional[str] = Query(default=None)):
    if _should_serve_coming_soon(preview):
        return FileResponse(STATIC_DIR / "coming-soon.html")
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/onderzoek", include_in_schema=False)
async def onderzoek(preview: Optional[str] = Query(default=None)):
    if _should_serve_coming_soon(preview):
        return FileResponse(STATIC_DIR / "coming-soon.html")
    return FileResponse(STATIC_DIR / "onderzoek.html")


@app.get("/admin", include_in_schema=False)
async def admin_page():
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/healthz")
async def healthz():
    return {"ok": True, "datasets": sorted(DATASETS_BY_LABEL.keys())}


@app.get("/api/datasets")
async def datasets():
    """Frontend's single source of truth for what to render. camelCase for JS."""
    def _source_types_for(ds) -> list[str]:
        if ds.source_type == "merged":
            return ["BGT", "OSM"]
        if ds.source_type == "osm":
            return ["OSM"]
        return ["BGT"]
    return [
        {
            "label":       d.label,
            "name":        d.name,
            "color":       d.color,
            "sourceType":  d.source_type,            # legacy single value
            "sourceTypes": _source_types_for(d),     # redesign array
            "defaultOn":   d.default_on,
            "featured":    d.featured,
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


@app.get("/api/coverage")
async def coverage():
    """Stats for the gap-analysis page: per-source counts + merged total."""
    bench_ds = DATASETS_BY_LABEL["bench"]
    if not hasattr(bench_ds, "bgt"):
        # Defensive: if Banken is ever swapped back to a non-composite, return zeros.
        return {"bgt_count": 0, "osm_count": 0, "merged_count": 0}
    bgt_markers, osm_markers = await asyncio.gather(
        bench_ds.bgt.fetch(app.state.client),
        bench_ds.osm.fetch(app.state.client),
    )
    merged = await bench_ds.fetch(app.state.client)
    return {
        "bgt_count": len(bgt_markers),
        "osm_count": len(osm_markers),
        "merged_count": len(merged),
    }


@app.get("/api/photos")
async def photos(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius: int = Query(default=50, ge=5, le=200, description="meters"),
    limit: int = Query(default=3, ge=1, le=10),
):
    """Nearby street-level photos via Mapillary. Empty list if no token or no coverage."""
    if not MAPILLARY_TOKEN:
        return {"photos": []}

    key = f"{lat:.5f},{lon:.5f},{radius},{limit}"

    async def _fetch() -> dict:
        # Progressive radius: precise first, expand to ~3× if no coverage. Benches
        # in side streets often have no drive-by within 50m but plenty within 150m.
        raw: list = []
        for try_radius in (radius, min(radius * 3, 200)):
            delta = try_radius / 111000  # degrees per meter, good enough at NL latitudes
            bbox = f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"
            r = await app.state.client.get(
                "https://graph.mapillary.com/images",
                params={
                    # is_pano=false: skip 360° panoramas (sparser) so we get
                    # ordinary street-level shots, which have far better coverage.
                    "access_token": MAPILLARY_TOKEN,
                    "bbox": bbox,
                    "is_pano": "false",
                    "limit": max(limit * 3, 10),
                    "fields": "id,thumb_256_url,thumb_1024_url,captured_at,compass_angle,geometry",
                },
                timeout=10.0,
            )
            r.raise_for_status()
            raw = r.json().get("data", [])
            if raw:
                break

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
        return {"photos": out}

    return await cached_proxy_fetch(photo_cache, key, _fetch, fallback={"photos": []})


# POI count within the radius → human level. Tunable; calibrated for ~150 m
# in Amsterdam, where a quiet residential street has few amenities and a
# centre block has dozens.
def _busyness_level(score: int) -> str:
    if score >= 50:
        return "druk"
    if score >= 15:
        return "gemiddeld"
    return "rustig"


@app.get("/api/busyness")
async def busyness(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius: int = Query(default=150, ge=25, le=500, description="meters"),
):
    """Neighbourhood-busyness proxy: density of nearby liveliness POIs (amenities,
    shops, transit) via Overpass. This approximates how lively the *area* is, NOT
    the real occupancy of the bench itself. Returns {score, level} (nulls on
    failure so the popup just omits the indicator)."""
    key = f"{lat:.4f},{lon:.4f},{radius}"

    query = (
        "[out:json][timeout:25];("
        f'node(around:{radius},{lat},{lon})["amenity"];'
        f'node(around:{radius},{lat},{lon})["shop"];'
        f'node(around:{radius},{lat},{lon})["public_transport"];'
        ");out count;"
    )

    async def _fetch() -> dict:
        r = await app.state.client.get(
            OVERPASS_URL,
            params={"data": query},
            timeout=25.0,
            headers={"User-Agent": "stephens-bankjes/1.0 (https://bankjes.stephenadei.nl)"},
        )
        r.raise_for_status()
        elements = r.json().get("elements") or []

        score = 0
        for el in elements:
            if el.get("type") == "count":
                score = int((el.get("tags") or {}).get("total", 0) or 0)
                break

        return {"score": score, "level": _busyness_level(score), "radius": radius}

    return await cached_proxy_fetch(
        busyness_cache,
        key,
        _fetch,
        fallback={"score": None, "level": None, "radius": radius},
    )
