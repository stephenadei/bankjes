"""API contract + smoke against the live env: the endpoints the map UI leans on return sane data."""

from collections import Counter

import pytest

from conftest import EXPECT_SHA

DAM = (52.3731, 4.8933)
VONDELPARK = (52.3582, 4.8686)
# Amsterdam incl. Weesp, with margin; markers outside this are a reprojection bug.
LAT, LON = (52.25, 52.47), (4.70, 5.15)


def test_deployed_version_is_this_commit(deployed):
    if not EXPECT_SHA:
        pytest.skip("QA_EXPECT_SHA unset")
    assert deployed == EXPECT_SHA, f"env serves {deployed!r}, expected {EXPECT_SHA}"


def test_healthz(api):
    r = api.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "bench" in body["datasets"]


def test_datasets_contract(api):
    r = api.get("/api/datasets")
    assert r.status_code == 200
    ds = r.json()
    assert {d["label"] for d in ds} >= {"bench"}
    for d in ds:
        assert {"label", "name", "color", "sourceTypes", "defaultOn"} <= d.keys()
    assert any(d["defaultOn"] for d in ds)


@pytest.fixture(scope="module")
def benches(api):
    r = api.get("/api/items", dataset="bench")
    assert r.status_code == 200, r.text[:200]
    return r.json()


def test_bench_items_sane(benches):
    items = benches["items"]
    assert benches["count"] == len(items)
    assert len(items) >= 300, "fewer benches than the BGT register alone (345)"
    assert len({i["id"] for i in items}) == len(items), "duplicate marker ids"
    sources = Counter(i["props"].get("source_type") for i in items)
    assert sources["bgt"] > 0 and sources["osm"] > 0, f"one register missing: {dict(sources)}"
    for i in items:
        assert i["dataset"] == "bench"
        assert LAT[0] < i["lat"] < LAT[1] and LON[0] < i["lon"] < LON[1], i


def test_items_bbox_filter(api, benches):
    s, w, n, e = 52.365, 4.88, 52.38, 4.905  # around Dam
    r = api.get("/api/items", dataset="bench", bbox=f"{s},{w},{n},{e}")
    assert r.status_code == 200
    inside = r.json()["items"]
    assert 0 < len(inside) < len(benches["items"])
    assert all(s <= i["lat"] <= n and w <= i["lon"] <= e for i in inside)


@pytest.mark.parametrize("params", [{"dataset": "nope"}, {"bbox": "not,a,bbox"}])
def test_items_rejects_bad_input(api, params):
    assert api.get("/api/items", **params).status_code == 400


def test_coverage(api):
    r = api.get("/api/coverage", tries=2)
    assert r.status_code == 200, f"{r.status_code} {r.text[:120]}"
    c = r.json()
    assert c["bgt_count"] > 0
    assert c["merged_count"] >= c["bgt_count"]
    if not c.get("degraded"):
        assert c["osm_count"] > 0
        assert c["merged_count"] <= c["bgt_count"] + c["osm_count"]


def test_photos_shape(api):
    r = api.get("/api/photos", lat=DAM[0], lon=DAM[1])
    assert r.status_code == 200
    for p in r.json()["photos"]:  # empty is allowed: no token or no coverage
        assert p["id"] and p["thumb"].startswith("https://")


def test_busyness_shape(api):
    r = api.get("/api/busyness", lat=DAM[0], lon=DAM[1])
    assert r.status_code == 200
    assert r.json()["level"] in ("rustig", "gemiddeld", "druk", None)  # None = upstream down, popup omits it


def test_route_dam_to_vondelpark(api):
    r = api.get("/api/route", from_lat=DAM[0], from_lon=DAM[1],
                to_lat=VONDELPARK[0], to_lon=VONDELPARK[1], mode="foot")
    assert r.status_code == 200, r.text[:200]
    route = r.json()
    assert route["engine"] in ("ors", "osrm")
    assert 1500 < route["distance_m"] < 5000  # ~2.7 km on foot
    assert len(route["geometry"]) >= 2 and route["steps"]


def test_route_wheelchair_needs_ors_or_says_so(api):
    r = api.get("/api/route", from_lat=DAM[0], from_lon=DAM[1],
                to_lat=VONDELPARK[0], to_lon=VONDELPARK[1], mode="wheelchair")
    assert r.status_code in (200, 503)  # 503 = no ORS key, a documented clean refusal


# acc/pre serve the app; only prd (APP_ENV=prd) swaps in coming-soon.html.
@pytest.mark.parametrize("path, marker", [("/", 'id="map"'), ("/onderzoek", "<title>Onderzoek")])
def test_pages_serve(api, path, marker):
    r = api.get(path)
    assert r.status_code == 200
    assert marker in r.text
