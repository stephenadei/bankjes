"""Tests for /api/coverage gap-analysis endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_coverage_endpoint_returns_counts():
    with TestClient(app) as client:
        r = client.get("/api/coverage")
        assert r.status_code == 200
        d = r.json()
        assert "bgt_count" in d
        assert "osm_count" in d
        assert "merged_count" in d
        assert d["merged_count"] <= d["bgt_count"] + d["osm_count"]
