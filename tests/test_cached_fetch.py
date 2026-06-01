"""Tests for the cached_fetch proxy helper.

Hermetic: no network. produce() is a plain coroutine; we assert on caching,
miss-then-fill, error-degradation, and the no-caching-of-failures guarantee.
"""

import httpx
import pytest
from cachetools import TTLCache

from app.cached_fetch import cached_fetch


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_without_calling_produce():
    cache = TTLCache(maxsize=8, ttl=60)
    cache["k"] = {"cached": True}
    calls = 0

    async def produce():
        nonlocal calls
        calls += 1
        return {"cached": False}

    out = await cached_fetch(cache, "k", produce, fallback={"fb": True})

    assert out == {"cached": True}
    assert calls == 0


@pytest.mark.asyncio
async def test_cache_miss_awaits_produce_caches_and_returns():
    cache = TTLCache(maxsize=8, ttl=60)

    async def produce():
        return {"value": 42}

    out = await cached_fetch(cache, "k", produce, fallback={"fb": True})

    assert out == {"value": 42}
    assert cache["k"] == {"value": 42}


@pytest.mark.asyncio
async def test_produce_called_once_on_repeated_hits():
    cache = TTLCache(maxsize=8, ttl=60)
    calls = 0

    async def produce():
        nonlocal calls
        calls += 1
        return calls

    first = await cached_fetch(cache, "k", produce, fallback=-1)
    second = await cached_fetch(cache, "k", produce, fallback=-1)

    assert first == 1
    assert second == 1  # served from cache, produce not re-run
    assert calls == 1


@pytest.mark.asyncio
async def test_http_error_returns_fallback_and_does_not_cache():
    cache = TTLCache(maxsize=8, ttl=60)

    async def produce():
        raise httpx.ConnectError("boom")

    out = await cached_fetch(cache, "k", produce, fallback={"photos": []})

    assert out == {"photos": []}
    assert "k" not in cache  # failure not pinned for the TTL


@pytest.mark.asyncio
async def test_value_error_returns_fallback_and_does_not_cache():
    cache = TTLCache(maxsize=8, ttl=60)

    async def produce():
        raise ValueError("bad json")

    fallback = {"score": None, "level": None, "radius": 150}
    out = await cached_fetch(cache, "k", produce, fallback=fallback)

    assert out == fallback
    assert "k" not in cache


@pytest.mark.asyncio
async def test_recovers_after_transient_failure():
    """A failure isn't cached, so the next call re-runs produce and can succeed."""
    cache = TTLCache(maxsize=8, ttl=60)
    attempts = 0

    async def produce():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("transient")
        return {"ok": True}

    first = await cached_fetch(cache, "k", produce, fallback={"ok": False})
    second = await cached_fetch(cache, "k", produce, fallback={"ok": False})

    assert first == {"ok": False}
    assert second == {"ok": True}
    assert cache["k"] == {"ok": True}


@pytest.mark.asyncio
async def test_unexpected_exception_propagates():
    """Only httpx.HTTPError / ValueError degrade; other errors are bugs, not
    upstream blips, so they must surface."""
    cache = TTLCache(maxsize=8, ttl=60)

    async def produce():
        raise KeyError("programmer error")

    with pytest.raises(KeyError):
        await cached_fetch(cache, "k", produce, fallback=None)
