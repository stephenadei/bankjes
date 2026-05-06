"""Smoke tests for the value types in app.domain.

The whole point of extracting Bbox/Marker as their own module is that they
become unit-testable without spinning up FastAPI or hitting upstream HTTP.
This file demonstrates that pay-off.
"""

import pytest

from app.domain import AMSTERDAM, Bbox, Marker


# ─── Bbox ──────────────────────────────────────────────────────────

def test_bbox_parse_round_trip():
    b = Bbox.parse("52.3,4.8,52.4,4.95")
    assert b == Bbox(south=52.3, west=4.8, north=52.4, east=4.95)


def test_bbox_parse_rejects_wrong_arity():
    with pytest.raises(ValueError, match="four comma-separated"):
        Bbox.parse("52.3,4.8,52.4")


def test_bbox_parse_rejects_non_numeric():
    with pytest.raises(ValueError, match="must be floats"):
        Bbox.parse("52.3,nope,52.4,4.95")


def test_bbox_rejects_inverted():
    with pytest.raises(ValueError, match="south must be <= north"):
        Bbox(south=52.4, west=4.8, north=52.3, east=4.95)


def test_bbox_contains_inclusive():
    b = AMSTERDAM
    # Centrum Dam (52.373, 4.893) — well inside
    assert b.contains(52.373, 4.893)
    # On the boundary — inclusive
    assert b.contains(b.south, b.west)
    # Outside (Den Haag-ish)
    assert not b.contains(52.08, 4.31)


def test_bbox_overpass_format():
    assert AMSTERDAM.as_overpass() == "52.295,4.745,52.43,5.02"


# ─── Marker ────────────────────────────────────────────────────────

def test_marker_accepts_valid():
    m = Marker(id="x", lat=52.37, lon=4.89, props={"k": "v"})
    assert m.lat == 52.37
    assert m.props == {"k": "v"}


def test_marker_rejects_out_of_range_lat():
    with pytest.raises(ValueError):
        Marker(id="x", lat=999.0, lon=0.0, props={})


def test_marker_default_props():
    m = Marker(id="x", lat=52.0, lon=4.0)
    assert m.props == {}
