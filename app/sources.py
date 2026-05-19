"""DataSource adapters and the registered DATASETS list.

A DataSource turns an HTTP client into a list of Markers. Two adapters
exist today: DsoSource (Amsterdam DSO open-data API) and OsmSource
(Overpass). Adding a third (PDOK, CKAN, …) means writing one more
adapter and appending it to DATASETS — nothing in main.py has to change.
"""

import math
import os
from dataclasses import dataclass, field
from typing import Optional, Protocol
from urllib.parse import urlencode

import httpx

from app.domain import AMSTERDAM, Bbox, Marker

DSO_BASE = "https://api.data.amsterdam.nl/v1"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Amsterdam DSO-API will require API keys eventually; warm-set now.
# Aanvragen via https://keys.api.data.amsterdam.nl/clients/v1/
AMSTERDAM_API_KEY: Optional[str] = os.environ.get("AMSTERDAM_API_KEY") or None

PAGE_SIZE = 1000
MAX_PAGES = 50


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in metres between two WGS84 coordinates.

    Standard Haversine formula. Good to within ~0.5% at the scale we
    use (sub-kilometre comparisons in Amsterdam).
    """
    r = 6_371_000.0  # mean Earth radius, metres
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _dedup_by_proximity(
    bgt_markers: list[Marker],
    osm_markers: list[Marker],
    radius_m: float,
) -> list[Marker]:
    """Merge two marker lists, dropping OSM markers within `radius_m` of any BGT marker.

    BGT markers are kept unconditionally (they carry the official
    identificatie field and are the canonical register). OSM markers
    that fall outside the dedup radius are appended. Each surviving
    BGT marker that absorbed one or more OSM matches gets a
    `merged_replicas: int` prop so popups can surface the overlap
    count.

    O(n × m) — fine at n ≈ 345, m ≈ 7000 with 1h cache TTL.
    """
    out: list[Marker] = []
    replica_counts: dict[str, int] = {}

    for b in bgt_markers:
        out.append(b)

    for o in osm_markers:
        absorbed = False
        for b in bgt_markers:
            if _haversine_m(b.lat, b.lon, o.lat, o.lon) <= radius_m:
                replica_counts[b.id] = replica_counts.get(b.id, 0) + 1
                absorbed = True
                break
        if not absorbed:
            out.append(o)

    # Re-emit BGT survivors with merged_replicas in props (Marker model
    # is immutable-ish since props is a dict but we keep it explicit).
    final: list[Marker] = []
    for m in out:
        if m.id in replica_counts:
            new_props = {**m.props, "merged_replicas": replica_counts[m.id]}
            final.append(Marker(id=m.id, lat=m.lat, lon=m.lon, props=new_props))
        else:
            final.append(m)
    return final


class DataSource(Protocol):
    """Interface for anything that yields a list of Markers from an HTTP client."""

    label: str
    name: str
    color: str
    source_type: str  # "dso" | "osm" — bubbled up to frontend for popup styling
    default_on: bool
    featured: bool

    async def fetch(self, client: httpx.AsyncClient) -> list[Marker]: ...


@dataclass
class DsoSource:
    """Amsterdam DSO open-data adapter. Walks paginated GeoJSON."""

    label: str
    name: str
    color: str
    path: str
    params: dict = field(default_factory=dict)
    default_on: bool = False
    featured: bool = False
    source_type: str = "dso"

    async def fetch(self, client: httpx.AsyncClient) -> list[Marker]:
        q = dict(self.params)
        q["_format"] = "geojson"
        q["_pageSize"] = PAGE_SIZE
        url: Optional[str] = f"{DSO_BASE}/{self.path}/?{urlencode(q)}"
        headers = {"X-API-Key": AMSTERDAM_API_KEY} if AMSTERDAM_API_KEY else None

        out: list[Marker] = []
        pages = 0
        while url and pages < MAX_PAGES:
            r = await client.get(url, timeout=30.0, headers=headers)
            r.raise_for_status()
            d = r.json()
            for feat in d.get("features") or []:
                marker = _feature_to_marker(feat)
                if marker is not None:
                    out.append(marker)
            url = _next_link(d.get("_links"))
            pages += 1
        return out


@dataclass
class OsmSource:
    """OpenStreetMap Overpass adapter. Single query, no pagination."""

    label: str
    name: str
    color: str
    overpass_query: str  # template using {s},{w},{n},{e}
    bbox: Bbox = AMSTERDAM
    default_on: bool = False
    featured: bool = False
    source_type: str = "osm"

    async def fetch(self, client: httpx.AsyncClient) -> list[Marker]:
        query = self.overpass_query.format(
            s=self.bbox.south, w=self.bbox.west,
            n=self.bbox.north, e=self.bbox.east,
        )
        r = await client.get(
            OVERPASS_URL,
            params={"data": query},
            timeout=60.0,
            headers={"User-Agent": "stephens-bankjes/1.0 (https://bankjes.stephensprive.app)"},
        )
        r.raise_for_status()
        d = r.json()
        out: list[Marker] = []
        for el in d.get("elements") or []:
            if el.get("type") != "node":
                continue
            lat = el.get("lat")
            lon = el.get("lon")
            if lat is None or lon is None:
                continue
            out.append(Marker(
                id=f'osm:{el["id"]}',
                lat=lat, lon=lon,
                props=el.get("tags") or {},
            ))
        return out


def _feature_to_marker(feat: dict) -> Optional[Marker]:
    """Turn one GeoJSON Point feature into a Marker, or None if unusable."""
    geom = feat.get("geometry") or {}
    if geom.get("type") != "Point":
        return None
    coords = geom.get("coordinates") or []
    if len(coords) < 2:
        return None
    props = feat.get("properties") or {}
    mid = feat.get("id") or props.get("identificatie") or props.get("id")
    if not mid:
        return None
    return Marker(id=str(mid), lat=coords[1], lon=coords[0], props=props)


def _next_link(links) -> Optional[str]:
    """Return the href of rel=next from a GeoJSON _links array, or None."""
    for link in links or []:
        if isinstance(link, dict) and link.get("rel") == "next":
            return link.get("href")
    return None


# ─── Registered datasets ──────────────────────────────────────────
# Single source of truth for backend AND frontend. /api/datasets
# returns this metadata; the map UI builds itself from it.

DATASETS: list[DataSource] = [
    DsoSource(
        label="bench",
        name="Banken",
        color="#5b7a3f",
        path="bgt/straatmeubilair",
        params={"plusType": "bank", "bronhouder": "G0363"},
        default_on=True,
        featured=True,
    ),
    OsmSource(
        label="bench_osm",
        name="Banken (OSM)",
        color="#4a5d6a",
        overpass_query='[out:json][timeout:30];node["amenity"="bench"]({s},{w},{n},{e});out;',
        default_on=True,
    ),
    DsoSource(
        label="picnic_table",
        name="Tafels",
        color="#7a8a47",
        path="bgt/straatmeubilair",
        params={"plusType": "picknicktafel", "bronhouder": "G0363"},
    ),
    DsoSource(
        label="trash_underground",
        name="Containers",
        color="#6b5d4f",
        path="huishoudelijkafval/containerlocatie",
    ),
    DsoSource(
        label="trash_surface",
        name="Afvalbakken",
        color="#a08770",
        path="objectenopenbareruimte/afvalbakken",
    ),
]

DATASETS_BY_LABEL: dict[str, DataSource] = {d.label: d for d in DATASETS}
