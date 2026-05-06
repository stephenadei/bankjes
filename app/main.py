"""Stephen's Bankjes — Amsterdam Street Furniture Explorer.

Pure-proxy FastAPI backend over the Amsterdam DSO open-data API.
No database; results are cached in memory with a short TTL so a busy
browser session does not hammer the upstream.
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx
from cachetools import TTLCache
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE = "https://api.data.amsterdam.nl/v1"

# (label, dataset/table path, query params)
# Amsterdam municipality code in the BGT bronhouder field. Without this filter
# the BGT endpoint returns straatmeubilair from neighbouring municipalities too
# (Hilversum, Almere, etc.) — the dataset is national, not Amsterdam-only.
AMSTERDAM_BRONHOUDER = "G0363"

DATASETS = [
    ("bench",            "bgt/straatmeubilair",                 {"plusType": "bank",          "bronhouder": AMSTERDAM_BRONHOUDER}),
    ("picnic_table",     "bgt/straatmeubilair",                 {"plusType": "picknicktafel", "bronhouder": AMSTERDAM_BRONHOUDER}),
    ("trash_bin",        "huishoudelijkafval/containerlocatie", {}),
    ("bike_pole",        "fietspaaltjes/fietspaaltjes",         {}),
    ("sports_facility",  "sport/openbaresportplek",             {}),
]

DATASET_LABELS = {label for label, _path, _q in DATASETS}

CACHE_TTL_SECONDS = 300
PAGE_SIZE = 1000
MAX_PAGES = 50  # hard cap to avoid runaway pagination

cache: TTLCache = TTLCache(maxsize=64, ttl=CACHE_TTL_SECONDS)


async def fetch_geojson(client: httpx.AsyncClient, path: str, params: dict) -> list[dict]:
    """Walk all pages of a dataset and return the merged feature list (WGS84)."""
    q = dict(params)
    q["_format"] = "geojson"
    q["_pageSize"] = PAGE_SIZE
    url: Optional[str] = f"{BASE}/{path}/?{urlencode(q)}"
    out: list[dict] = []
    pages = 0
    while url and pages < MAX_PAGES:
        r = await client.get(url, timeout=30.0)
        r.raise_for_status()
        d = r.json()
        out.extend(d.get("features") or [])
        url = None
        for link in d.get("_links") or []:
            if isinstance(link, dict) and link.get("rel") == "next":
                url = link.get("href")
                break
        pages += 1
    return out


def feature_to_marker(label: str, feat: dict) -> Optional[dict]:
    geom = feat.get("geometry") or {}
    if geom.get("type") != "Point":
        return None
    coords = geom.get("coordinates") or []
    if len(coords) < 2:
        return None
    props = feat.get("properties") or {}
    return {
        "id": feat.get("id") or props.get("identificatie") or props.get("id"),
        "dataset": label,
        "lat": coords[1],
        "lon": coords[0],
        "props": props,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=30.0)
    yield
    await app.state.client.aclose()


app = FastAPI(title="Stephen's Bankjes — Amsterdam Street Furniture", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/healthz")
async def healthz():
    return {"ok": True, "datasets": sorted(DATASET_LABELS)}


@app.get("/api/items")
async def items(
    dataset: Optional[str] = Query(default=None, description="One of: " + ", ".join(sorted(DATASET_LABELS))),
    bbox: Optional[str] = Query(default=None, description="south,west,north,east in WGS84"),
):
    if dataset is not None and dataset not in DATASET_LABELS:
        raise HTTPException(status_code=400, detail=f"Unknown dataset: {dataset}")

    bb = None
    if bbox:
        try:
            parts = [float(x) for x in bbox.split(",")]
            if len(parts) != 4:
                raise ValueError
            bb = parts  # south, west, north, east
        except ValueError:
            raise HTTPException(status_code=400, detail="bbox must be 'south,west,north,east'")

    targets = [d for d in DATASETS if dataset is None or d[0] == dataset]

    async def get_one(label, path, q):
        key = (label, frozenset(q.items()))
        if key in cache:
            return cache[key]
        feats = await fetch_geojson(app.state.client, path, q)
        cache[key] = feats
        return feats

    results = await asyncio.gather(*[get_one(*t) for t in targets])

    out: list[dict] = []
    for (label, _path, _q), features in zip(targets, results):
        for feat in features:
            m = feature_to_marker(label, feat)
            if m is None:
                continue
            if bb and not (bb[0] <= m["lat"] <= bb[2] and bb[1] <= m["lon"] <= bb[3]):
                continue
            out.append(m)

    return {"count": len(out), "items": out}
