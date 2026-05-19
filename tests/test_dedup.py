"""Tests for proximity dedup helpers in app.sources."""
import math
import pytest

from app.sources import _haversine_m


def test_haversine_zero():
    assert _haversine_m(52.37, 4.90, 52.37, 4.90) == pytest.approx(0.0, abs=0.01)


def test_haversine_one_degree_lat():
    # 1° latitude ≈ 111_000 m anywhere on Earth
    d = _haversine_m(52.0, 4.9, 53.0, 4.9)
    assert 110_900 < d < 111_200


def test_haversine_small_amsterdam():
    # Two points ~10m apart in Amsterdam centre
    d = _haversine_m(52.3676, 4.9041, 52.3676, 4.9042)
    # 1° lon at 52.37° lat ≈ 67_900 m; 0.0001° ≈ 6.8 m
    assert 6 < d < 8


def test_haversine_asymmetry_safety():
    # Distance is symmetric
    d1 = _haversine_m(52.37, 4.90, 52.38, 4.91)
    d2 = _haversine_m(52.38, 4.91, 52.37, 4.90)
    assert d1 == pytest.approx(d2, abs=0.001)


from app.domain import Marker
from app.sources import _dedup_by_proximity


def _m(id_: str, lat: float, lon: float) -> Marker:
    return Marker(id=id_, lat=lat, lon=lon, props={})


def test_dedup_keeps_all_when_no_overlap():
    bgt = [_m("b1", 52.37, 4.90)]
    osm = [_m("o1", 52.40, 4.95)]  # far away
    out = _dedup_by_proximity(bgt, osm, 10)
    ids = {m.id for m in out}
    assert ids == {"b1", "o1"}


def test_dedup_drops_osm_within_radius():
    bgt = [_m("b1", 52.37, 4.90)]
    # ~6.8m east of b1
    osm = [_m("o1", 52.37, 4.9001)]
    out = _dedup_by_proximity(bgt, osm, 10)
    ids = {m.id for m in out}
    assert ids == {"b1"}, "OSM marker within 10m of BGT should be dropped"


def test_dedup_keeps_osm_just_outside_radius():
    bgt = [_m("b1", 52.37, 4.90)]
    # ~15m east of b1 (0.00022° lon)
    osm = [_m("o1", 52.37, 4.90022)]
    out = _dedup_by_proximity(bgt, osm, 10)
    ids = {m.id for m in out}
    assert ids == {"b1", "o1"}


def test_dedup_bgt_always_kept():
    # Multiple BGT markers within 10m of each other are all kept
    # (dedup only applies BGT-vs-OSM, not BGT-vs-BGT).
    bgt = [
        _m("b1", 52.37, 4.90),
        _m("b2", 52.37, 4.9001),  # 6.8m apart
    ]
    osm = []
    out = _dedup_by_proximity(bgt, osm, 10)
    assert len(out) == 2


def test_dedup_marks_replicas_on_survivor():
    bgt = [_m("b1", 52.37, 4.90)]
    osm = [
        _m("o1", 52.37, 4.9001),    # ~6.8m
        _m("o2", 52.37, 4.90008),   # ~5.4m
    ]
    out = _dedup_by_proximity(bgt, osm, 10)
    assert len(out) == 1
    survivor = out[0]
    assert survivor.id == "b1"
    assert survivor.props.get("merged_replicas") == 2
