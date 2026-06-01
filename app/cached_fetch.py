"""Cached proxy-fetch helper.

Both /api/photos and /api/busyness share the same pure-proxy shape: check a
TTLCache, call upstream on a miss, cache the success, and on an upstream error
log a warning and return a caller-supplied fallback *without* caching the
failure (so a transient upstream blip doesn't get pinned for the full TTL).
This factors that pattern into one place.
"""

import logging
from typing import Awaitable, Callable, Hashable, TypeVar

import httpx

log = logging.getLogger("uvicorn.error")

T = TypeVar("T")


async def cached_fetch(
    cache,
    key: Hashable,
    produce: Callable[[], Awaitable[T]],
    fallback: T,
) -> T:
    """Return ``cache[key]`` if present, else ``await produce()``.

    On a cache hit the cached value is returned untouched. On a miss the
    coroutine returned by ``produce`` is awaited; its result is cached and
    returned. If ``produce`` raises ``httpx.HTTPError`` or ``ValueError`` (the
    upstream-failure shapes the proxy endpoints care about), a warning is
    logged and ``fallback`` is returned — the failure is *not* cached.
    """
    if key in cache:
        return cache[key]
    try:
        value = await produce()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("cached_fetch upstream failed for %s: %s", key, e)
        return fallback
    cache[key] = value
    return value
