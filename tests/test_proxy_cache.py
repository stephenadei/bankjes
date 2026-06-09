"""Hermetic tests for the cached-proxy-fetch seam (issue #14).

No network: ``compute`` is a plain coroutine, so these exercise the cache +
graceful-degradation contract directly.
"""

import httpx
from cachetools import TTLCache

from app.proxy_cache import cached_proxy_fetch


async def test_miss_runs_compute_and_stores():
    cache: TTLCache = TTLCache(maxsize=8, ttl=60)
    calls = {"n": 0}

    async def compute():
        calls["n"] += 1
        return {"v": 1}

    out = await cached_proxy_fetch(cache, "k", compute, fallback={"v": 0})

    assert out == {"v": 1}
    assert cache["k"] == {"v": 1}
    assert calls["n"] == 1


async def test_hit_skips_compute():
    cache: TTLCache = TTLCache(maxsize=8, ttl=60)
    cache["k"] = {"v": 42}

    async def compute():
        raise AssertionError("compute must not run on a cache hit")

    out = await cached_proxy_fetch(cache, "k", compute, fallback={"v": 0})

    assert out == {"v": 42}


async def test_http_error_returns_fallback_and_does_not_cache():
    cache: TTLCache = TTLCache(maxsize=8, ttl=60)

    async def compute():
        raise httpx.ConnectError("boom")

    out = await cached_proxy_fetch(cache, "k", compute, fallback={"v": 0})

    assert out == {"v": 0}
    # fallback is NOT cached: the next request retries the upstream
    assert "k" not in cache


async def test_value_error_returns_fallback():
    cache: TTLCache = TTLCache(maxsize=8, ttl=60)

    async def compute():
        raise ValueError("malformed json")

    out = await cached_proxy_fetch(cache, "k", compute, fallback={"v": 0})

    assert out == {"v": 0}
    assert "k" not in cache
