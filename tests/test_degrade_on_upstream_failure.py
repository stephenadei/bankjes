"""One dead register must not blank the map — and must not fake a finding.

On 2026-09-24 Overpass returned 504 for the Amsterdam bench query. The merge
gathered both sources without return_exceptions, so the first failure cancelled
its sibling: the 345 healthy BGT markers went down with OSM, /api/items?dataset=bench
returned 500, and BOTH panels of /onderzoek rendered empty from a fault in one
upstream.

The negative cases matter more than the positive ones here. Degrading is only safe
if it cannot be mistaken for a complete read.
"""

import asyncio

import httpx
import pytest

from app.domain import Marker
from app.sources import MergedBenchSource


class _Fixed:
    """A DataSource that returns what it was given, or raises it."""

    label = "_fixed"
    name = "fixed"
    color = "#000"
    source_type = "dso"
    default_on = False
    featured = False

    def __init__(self, result):
        self._result = result

    async def fetch(self, client):
        if isinstance(self._result, BaseException):
            raise self._result
        return self._result


def _m(id_, lat, lon):
    return Marker(id=id_, lat=lat, lon=lon, props={})


BOOM = httpx.HTTPStatusError("504", request=None, response=None)


def _merge(bgt, osm, dedup_m=10):
    src = MergedBenchSource(bgt=_Fixed(bgt), osm=_Fixed(osm), dedup_m=dedup_m)
    return asyncio.run(src.fetch(client=None))


# ── degrade, do not die ─────────────────────────────────────────────────

def test_osm_down_still_serves_bgt():
    # The exact 2026-09-24 shape: Overpass 504, official register fine.
    out = _merge([_m("b1", 52.37, 4.90)], BOOM)
    assert [m.id for m in out] == ["b1"]


def test_bgt_down_still_serves_osm():
    out = _merge(BOOM, [_m("o1", 52.37, 4.90)])
    assert [m.id for m in out] == ["o1"]


def test_survivors_keep_their_provenance_when_degraded():
    # The reason degrading is safe: a caller counting by source sees the real
    # shortfall instead of a silently smaller total.
    out = _merge([_m("b1", 52.37, 4.90)], BOOM)
    assert out[0].props["source_type"] == "bgt"


# ── what must STILL fail ────────────────────────────────────────────────

def test_both_down_is_an_error():
    # Nothing was fetched. Returning [] here would cache emptiness as an answer
    # and blank the map for the full TTL.
    with pytest.raises(RuntimeError, match="both registers failed"):
        _merge(BOOM, BOOM)


def test_an_empty_register_is_not_a_failure():
    # A register that genuinely answers "no benches" is data, not an outage, and
    # must not be confused with one.
    out = _merge([_m("b1", 52.37, 4.90)], [])
    assert len(out) == 1


# ── the merge still merges ──────────────────────────────────────────────

def test_dedup_is_unchanged_when_both_answer():
    bgt = [_m("b1", 52.37, 4.90)]
    osm = [_m("o-near", 52.37, 4.9001), _m("o-far", 52.40, 4.95)]  # ~6.8m, ~4km
    out = _merge(bgt, osm)
    ids = {m.id for m in out}
    assert ids == {"b1", "o-far"}
    survivor = next(m for m in out if m.id == "b1")
    assert survivor.props["merged_replicas"] == 1


def test_register_sizes_are_recoverable_from_the_merged_set():
    # /api/coverage derives the ORIGINAL counts from one fetch this way, instead
    # of re-reading both upstreams a second time.
    bgt = [_m("b1", 52.37, 4.90)]
    osm = [_m("o-near", 52.37, 4.9001), _m("o-far", 52.40, 4.95)]
    out = _merge(bgt, osm)

    n_bgt = sum(1 for m in out if m.props.get("source_type") == "bgt")
    n_osm_surviving = sum(1 for m in out if m.props.get("source_type") == "osm")
    absorbed = sum(int(m.props.get("merged_replicas") or 0) for m in out)

    assert n_bgt == len(bgt)
    assert n_osm_surviving + absorbed == len(osm)
    # The conservation invariant test_coverage.py asserts against live data.
    assert len(out) <= n_bgt + (n_osm_surviving + absorbed)
