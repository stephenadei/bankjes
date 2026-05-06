"""Stephen's Bankjes — Amsterdam Street Furniture Explorer.

Pure-proxy FastAPI backend. Banken komen uit OSM Overpass (echte coverage,
incl. centrum Amsterdam) — de andere 4 categorieën komen uit het Amsterdam
DSO open-data portaal. Geen DB; in-memory TTL cache.
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

DSO_BASE = "https://api.data.amsterdam.nl/v1"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Amsterdam-stadsdelen, bewust zonder Weesp (Weesp domineert BGT-data).
AMS_BBOX = (52.295, 4.745, 52.430, 5.020)  # south, west, north, east

# Each dataset has a label + source-specific config.
# DSO sources use a path under DSO_BASE; OSM uses an Overpass query template.
DATASETS = [
    # Primair — Amsterdam-officieel via data.amsterdam.nl (DSO)
    {
        "label":  "bench",
        "source": "dso",
        "path":   "bgt/straatmeubilair",
        "params": {"plusType": "bank", "bronhouder": "G0363"},
    },
    {
        "label":  "picnic_table",
        "source": "dso",
        "path":   "bgt/straatmeubilair",
        "params": {"plusType": "picknicktafel", "bronhouder": "G0363"},
    },
    {
        "label":  "trash_bin",
        "source": "dso",
        "path":   "huishoudelijkafval/containerlocatie",
        "params": {},
    },
    {
        "label":  "bike_pole",
        "source": "dso",
        "path":   "fietspaaltjes/fietspaaltjes",
        "params": {},
    },
    {
        "label":  "sports_facility",
        "source": "dso",
        "path":   "sport/openbaresportplek",
        "params": {},
    },
    # Secundair — aanvullende crowd-sourced laag voor banken (OSM)
    {
        "label":  "bench_osm",
        "source": "osm",
        "query":  '[out:json][timeout:30];node["amenity"="bench"]({s},{w},{n},{e});out;',
    },
]

DATASET_LABELS = {d["label"] for d in DATASETS}

CACHE_TTL_SECONDS = 300
PAGE_SIZE = 1000
MAX_PAGES = 50

cache: TTLCache = TTLCache(maxsize=64, ttl=CACHE_TTL_SECONDS)


async def fetch_dso(client: httpx.AsyncClient, path: str, params: dict) -> list[dict]:
    """Walk all pages of a DSO dataset and return marker-shaped dicts (WGS84)."""
    q = dict(params)
    q["_format"] = "geojson"
    q["_pageSize"] = PAGE_SIZE
    url: Optional[str] = f"{DSO_BASE}/{path}/?{urlencode(q)}"
    out: list[dict] = []
    pages = 0
    while url and pages < MAX_PAGES:
        r = await client.get(url, timeout=30.0)
        r.raise_for_status()
        d = r.json()
        for feat in d.get("features") or []:
            geom = feat.get("geometry") or {}
            if geom.get("type") != "Point":
                continue
            coords = geom.get("coordinates") or []
            if len(coords) < 2:
                continue
            props = feat.get("properties") or {}
            out.append({
                "id":   feat.get("id") or props.get("identificatie") or props.get("id"),
                "lat":  coords[1],
                "lon":  coords[0],
                "props": props,
            })
        url = None
        for link in d.get("_links") or []:
            if isinstance(link, dict) and link.get("rel") == "next":
                url = link.get("href")
                break
        pages += 1
    return out


async def fetch_overpass(client: httpx.AsyncClient, query_template: str) -> list[dict]:
    """Run an Overpass query and return marker-shaped dicts."""
    s, w, n, e = AMS_BBOX
    query = query_template.format(s=s, w=w, n=n, e=e)
    # Overpass accepteert GET of POST application/x-www-form-urlencoded.
    # We sturen GET — eenvoudiger en niet gevoelig voor de Accept-default van httpx.
    r = await client.get(
        OVERPASS_URL,
        params={"data": query},
        timeout=60.0,
        headers={"User-Agent": "stephens-bankjes/1.0 (https://bankjes.stephensprive.app)"},
    )
    r.raise_for_status()
    d = r.json()
    out: list[dict] = []
    for el in d.get("elements") or []:
        if el.get("type") != "node":
            continue
        if "lat" not in el or "lon" not in el:
            continue
        out.append({
            "id":   f'osm:{el["id"]}',
            "lat":  el["lat"],
            "lon":  el["lon"],
            "props": el.get("tags") or {},
        })
    return out


async def fetch_dataset(client: httpx.AsyncClient, ds: dict) -> list[dict]:
    """Dispatch by source."""
    if ds["source"] == "osm":
        return await fetch_overpass(client, ds["query"])
    return await fetch_dso(client, ds["path"], ds["params"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=60.0)
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

    targets = [d for d in DATASETS if dataset is None or d["label"] == dataset]

    async def get_one(ds):
        key = ds["label"]
        if key in cache:
            return cache[key]
        items = await fetch_dataset(app.state.client, ds)
        cache[key] = items
        return items

    results = await asyncio.gather(*[get_one(t) for t in targets])

    out: list[dict] = []
    for ds, items_for_ds in zip(targets, results):
        label = ds["label"]
        for it in items_for_ds:
            if bb and not (bb[0] <= it["lat"] <= bb[2] and bb[1] <= it["lon"] <= bb[3]):
                continue
            out.append({**it, "dataset": label})

    return {"count": len(out), "items": out}
