"""Tests for /api/coverage gap-analysis endpoint.

Hits real upstream DSO + Overpass via the app's httpx client. Skipped
in CI / when the upstream is unreachable. Run manually on the dev
machine with a warm cache for a clean signal.
"""

import os

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="hits live DSO + Overpass — flaky on GHA runners",
)
def test_coverage_endpoint_returns_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("BANKJES_DB_PATH", str(tmp_path / "test.db"))
    try:
        with TestClient(app) as client:
            r = client.get("/api/coverage")
    except httpx.HTTPError:
        pytest.skip("upstream unreachable")
    assert r.status_code == 200
    d = r.json()
    assert "bgt_count" in d
    assert "osm_count" in d
    assert "merged_count" in d
    assert d["merged_count"] <= d["bgt_count"] + d["osm_count"]
