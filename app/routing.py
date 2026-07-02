"""Route proxy — OpenRouteService, normalized to our own contract.

The frontend never sees ORS's response shape: /api/route returns a
normalized route so the engine stays swappable (self-hosted ORS, Valhalla)
without frontend changes. Only the initial route and the occasional
reroute call this; the live turn-by-turn loop is client-side geometry.

Guards, because the endpoint fronts a keyed upstream on a public site:
coords must be near Amsterdam (this is not a free world-router) and a
daily budget stays under ORS's free tier.
"""

import math
import os
import time
from typing import Optional

import httpx

ORS_URL = "https://api.openrouteservice.org/v2/directions/{profile}/geojson"

# mode (our contract) → ORS profile
PROFILES = {
    "foot": "foot-walking",
    "bike": "cycling-regular",
    "wheelchair": "wheelchair",
}

AMS_CENTER = (52.3728, 4.8936)
MAX_KM_FROM_AMS = 50  # generous NL-Randstad radius; blocks world-router abuse

# Daily budget, kept under ORS's 2000/day free tier. In-memory is fine:
# single process, and a restart resetting the counter only risks a slightly
# early 429-free day, never overspend by more than the remainder.
DAILY_BUDGET = 1500
_budget_day: Optional[str] = None
_budget_used = 0


def api_key() -> Optional[str]:
    """Read per call (not import time) so tests and env changes take effect."""
    return os.environ.get("ORS_API_KEY") or None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def coords_in_service_area(lat: float, lon: float) -> bool:
    return _haversine_km(lat, lon, *AMS_CENTER) <= MAX_KM_FROM_AMS


def budget_allows() -> bool:
    """Count a request against today's budget; False once spent."""
    global _budget_day, _budget_used
    today = time.strftime("%Y-%m-%d")
    if _budget_day != today:
        _budget_day, _budget_used = today, 0
    if _budget_used >= DAILY_BUDGET:
        return False
    _budget_used += 1
    return True


def normalize(ors_geojson: dict) -> dict:
    """ORS directions/geojson → our engine-agnostic route contract.

    Raises ValueError on an unexpected shape (cached_fetch treats that as an
    upstream failure, so a malformed answer is never cached).
    """
    try:
        feature = ors_geojson["features"][0]
        coords = feature["geometry"]["coordinates"]  # [[lon, lat], …]
        props = feature["properties"]
        summary = props["summary"]
        segments = props["segments"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"unexpected ORS shape: {e}") from e

    geometry = [[c[1], c[0]] for c in coords]  # → [[lat, lon], …]
    steps = []
    for seg in segments:
        for st in seg.get("steps", []):
            idx = (st.get("way_points") or [0])[0]
            idx = min(max(idx, 0), len(geometry) - 1)
            steps.append(
                {
                    "instruction": st.get("instruction", ""),
                    "distance_m": round(st.get("distance", 0)),
                    "duration_s": round(st.get("duration", 0)),
                    "maneuver_point": geometry[idx],
                    "geometry_idx": idx,
                    "type": st.get("type", -1),
                }
            )
    return {
        "geometry": geometry,
        "distance_m": round(summary.get("distance", 0)),
        "duration_s": round(summary.get("duration", 0)),
        "steps": steps,
    }


async def fetch_route(
    client: httpx.AsyncClient,
    key: str,
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    mode: str,
) -> dict:
    """One ORS directions call → normalized route. Raises httpx.HTTPError
    on upstream trouble, ValueError on a malformed answer."""
    r = await client.post(
        ORS_URL.format(profile=PROFILES[mode]),
        headers={"Authorization": key},
        json={
            "coordinates": [[from_lon, from_lat], [to_lon, to_lat]],
            "language": "nl",
            "instructions": True,
        },
        timeout=15.0,
    )
    if r.status_code != 200:
        r.raise_for_status()
    return normalize(r.json())
