"""Headless-browser QA of the map UI: loads, renders benches, filter/search/detail flows work, no errors.

One desktop page is shared by the ordered tests below (loading costs ~10 s: a 5 s minimum loader
plus the cold upstream fetch); the mobile check gets its own context.
"""

import hashlib
import re

import pytest
from playwright.sync_api import expect, sync_playwright

from conftest import ARTIFACTS, BASE_URL

LOAD_TIMEOUT_MS = 120_000  # first visitor after a deploy pays the cold Overpass fetch
# Anonymous visitor: /api/me answers 401 by design (fetchMe → shows the login button).
EXPECTED_HTTP_ERRORS = {("/api/me", 401)}
XYZ_TILE = re.compile(r"/\d+/\d+/\d+(@2x)?\.(png|jpe?g|webp)")  # basemap tile of any provider


@pytest.fixture(scope="session")
def pw():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(pw):
    b = pw.chromium.launch()
    yield b
    b.close()


def _watch(page):
    """Collect what a human would see in devtools: JS exceptions, console errors, failing requests."""
    problems = []
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    page.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text
            and problems.append(f"console.error: {m.text[:200]}"))

    def on_response(r):
        path = r.url.removeprefix(BASE_URL).split("?")[0]
        if r.url.startswith(BASE_URL) and r.status >= 400 and (path, r.status) not in EXPECTED_HTTP_ERRORS:
            problems.append(f"HTTP {r.status} {path}")

    page.on("response", on_response)
    page.on("requestfailed", lambda r: r.url.startswith(BASE_URL)
            and problems.append(f"request failed: {r.url} {r.failure}"))
    return problems


def _open(page):
    page.goto(BASE_URL + "/", wait_until="load")
    page.wait_for_selector("#bj-loader", state="detached", timeout=LOAD_TIMEOUT_MS)


def _count(page, sel="#bj-visible-count"):
    return int(page.inner_text(sel).replace(".", "") or 0)  # nl-NL thousands separator


def _shot_on_failure(request, page):
    rep = getattr(request.node, "rep_call", None)
    if rep is not None and rep.failed:
        page.screenshot(path=ARTIFACTS / f"fail-{request.node.name}.png", full_page=True)


@pytest.fixture(scope="module")
def desktop(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, locale="nl-NL")
    page = ctx.new_page()
    page.problems = _watch(page)
    page.tiles = []
    page.on("response", lambda r: XYZ_TILE.search(r.url) and page.tiles.append(r))
    _open(page)
    yield page
    ctx.close()


@pytest.fixture
def page(desktop, request):
    yield desktop
    _shot_on_failure(request, desktop)


def test_map_renders_with_benches(page):
    expect(page.locator("#map .leaflet-tile-loaded").first).to_be_visible()
    expect(page.locator("#map .leaflet-marker-icon").first).to_be_visible()
    assert _count(page) > 100, "benches visible in the default Amsterdam view"
    assert page.locator("#bj-filter-row .bj-pill").count() >= 2
    page.screenshot(path=ARTIFACTS / "desktop-home.png")


def _digest(response):
    try:
        return hashlib.sha1(response.body()).hexdigest()
    except Exception:  # body evicted from the browser cache
        return None


def test_basemap_tiles_are_real(page):
    """A broken basemap still 'loads': without an API key CARTO serves one identical
    'API KEY REQUIRED' PNG for every tile. Real map tiles differ from each other."""
    digests = {d for d in map(_digest, page.tiles) if d}
    assert len(page.tiles) >= 4, "no basemap tiles requested"
    assert len(digests) > 1, f"all {len(page.tiles)} basemap tiles are the same image (CARTO watermark?)"


def test_both_bench_registers_on_the_map(page):
    """The whole point of the app: BGT and OSM benches side by side (ADR-0001)."""
    for src in ("BGT", "OSM"):
        n = page.inner_text(f'#bj-filter-row .bj-pill[data-key="bench"][data-source="{src}"] .bj-pill-count')
        assert n.strip() not in ("", "0"), f"{src} bench pill counts {n!r}"


def test_backrest_filter_narrows_and_restores(page):
    before = _count(page)
    mod = page.locator("#bj-rugleun")
    mod.click()
    expect(mod).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#bj-visible-count")).not_to_have_text(f"{before:,}".replace(",", "."))
    assert 0 < _count(page) < before
    page.locator("#bj-rugleun").click()
    expect(page.locator("#bj-visible-count")).to_have_text(f"{before:,}".replace(",", "."))


def test_dataset_pill_loads_its_layer(page):
    pill = page.locator('#bj-filter-row .bj-pill[data-key="picnic_table"]')
    with page.expect_response(lambda r: "/api/items?dataset=picnic_table" in r.url) as resp:
        pill.click()
    assert resp.value.status == 200
    expect(page.locator('#bj-filter-row .bj-pill[data-key="picnic_table"]')).to_have_class(re.compile(r"\bon\b"))
    page.locator('#bj-filter-row .bj-pill[data-key="picnic_table"]').click()
    expect(page.locator('#bj-filter-row .bj-pill[data-key="picnic_table"]')).not_to_have_class(re.compile(r"\bon\b"))


def test_search_flies_to_place(page):
    before = page.inner_text("#bj-visible-count")
    page.fill("#bj-search-input", "Dam")
    row = page.locator(".bj-suggest-row", has=page.locator(".bj-suggest-label", has_text=re.compile(r"^Dam$"))).first
    row.click()
    expect(page.locator("#bj-suggest")).to_be_hidden()
    expect(page.locator("#bj-search-input")).to_have_value("Dam")
    expect(page.locator("#bj-visible-count")).not_to_have_text(before)  # zoomed 13 → 16 on Dam
    assert _count(page) > 0, "no benches around Dam"
    page.screenshot(path=ARTIFACTS / "desktop-search.png")


def test_bench_detail_popup(page):
    page.click("#bj-pull-tab")
    expect(page.locator("#bj-sidebar")).to_have_class(re.compile(r"\bopen\b"))
    page.locator("#bj-sidebar-list .bj-sheet-row").first.click()
    popup = page.locator(".bj-popup")
    expect(popup).to_be_visible()
    expect(popup.locator(".bj-popup-title")).not_to_be_empty()
    expect(page.locator("#bj-popup-route")).to_be_visible()
    page.screenshot(path=ARTIFACTS / "desktop-detail.png")


def test_no_errors_in_browser(page):
    assert page.problems == []


def test_mobile_loads_with_sheet(pw, browser):
    ctx = browser.new_context(**pw.devices["Pixel 7"], locale="nl-NL")
    mobile = ctx.new_page()
    problems = _watch(mobile)
    try:
        _open(mobile)
        expect(mobile.locator("#map .leaflet-marker-icon").first).to_be_visible()
        expect(mobile.locator("#bj-sheet")).to_be_visible()
        assert _count(mobile, "#bj-mobile-visible-count") > 100
        mobile.screenshot(path=ARTIFACTS / "mobile-home.png")
        assert problems == []
    except Exception:
        mobile.screenshot(path=ARTIFACTS / "fail-test_mobile_loads_with_sheet.png")
        raise
    finally:
        ctx.close()
