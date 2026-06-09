"""Cached proxy-fetch seam shared by the upstream-proxy endpoints.

The Mapillary-photos and Overpass-busyness handlers each used to inline the same
check→fetch→store→degrade-on-error dance. That made them shallow: their interface
("given coords, give a shaped result") was nearly as complex as their body. This
module is that seam — caching plus "fall back instead of raising when the upstream
fails" — so each endpoint keeps only its own shaping.
"""

import logging
from typing import Awaitable, Callable, TypeVar

import httpx
from cachetools import TTLCache

log = logging.getLogger("uvicorn.error")

T = TypeVar("T")


async def cached_proxy_fetch(
    cache: TTLCache,
    key: str,
    compute: Callable[[], Awaitable[T]],
    *,
    fallback: T,
) -> T:
    """Return ``cache[key]`` if present, else run ``compute`` and store its result.

    ``compute`` does the upstream call plus the endpoint's own shaping. If it
    raises an httpx error (connection failure, non-2xx via ``raise_for_status``)
    or a JSON ``ValueError``, ``fallback`` is returned and is NOT cached — so the
    next request retries the upstream instead of serving a degraded result.
    """
    if key in cache:
        return cache[key]
    try:
        result = await compute()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("cached proxy fetch failed for %s: %s", key, e)
        return fallback
    cache[key] = result
    return result
