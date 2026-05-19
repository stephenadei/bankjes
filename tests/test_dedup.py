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
