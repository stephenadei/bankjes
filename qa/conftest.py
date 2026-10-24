"""Post-deploy QA against a live env (docs/qa.md). Not hermetic: hits the real URL and its upstreams.

    QA_BASE_URL=https://bankjes-acc.stephensprive.app pytest qa

QA_EXPECT_SHA: commit the env must serve (/healthz version); unset = skip that check.
QA_ARTIFACTS:  where screenshots + results.md go (default qa-artifacts/).
"""

import os
import time
from pathlib import Path

import httpx
import pytest

BASE_URL = os.environ.get("QA_BASE_URL", "").rstrip("/")
EXPECT_SHA = os.environ.get("QA_EXPECT_SHA", "")
ARTIFACTS = Path(os.environ.get("QA_ARTIFACTS", "qa-artifacts"))
DEPLOY_TIMEOUT_S = int(os.environ.get("QA_DEPLOY_TIMEOUT", "240"))

_started = time.time()


def pytest_configure(config):
    if not BASE_URL:
        raise pytest.UsageError("set QA_BASE_URL, e.g. https://bankjes-acc.stephensprive.app")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)


class Api:
    """GET with a short retry on 5xx/transport errors: upstreams (Overpass, DSO) flake."""

    def __init__(self):
        self.client = httpx.Client(base_url=BASE_URL, timeout=90.0, follow_redirects=True)

    def get(self, path, tries=3, **params):
        for attempt in range(tries):
            try:
                r = self.client.get(path, params=params or None)
                if r.status_code < 500 or attempt == tries - 1:
                    return r
            except httpx.TransportError:
                if attempt == tries - 1:
                    raise
            time.sleep(10)


@pytest.fixture(scope="session")
def api():
    a = Api()
    yield a
    a.client.close()


@pytest.fixture(scope="session", autouse=True)
def deployed(api):
    """Wait until the env answers /healthz (and serves QA_EXPECT_SHA); returns the version seen."""
    deadline, seen = time.time() + DEPLOY_TIMEOUT_S, None
    while time.time() < deadline:
        try:
            r = api.client.get("/healthz", timeout=10)
            if r.status_code == 200:
                seen = r.json().get("version")
                if not EXPECT_SHA or seen == EXPECT_SHA:
                    return seen
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(5)
    return seen


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    rep = yield
    setattr(item, f"rep_{rep.when}", rep)  # page fixtures read this to screenshot failures
    return rep


ICON = {"failed": "❌", "error": "❌", "passed": "✅", "skipped": "⏭️"}


def _reason(rep):
    crash = getattr(rep.longrepr, "reprcrash", None)
    text = crash.message if crash else str(rep.longrepr or "")
    return text.splitlines()[0][:160].replace("|", "\\|") if text else ""


def pytest_terminal_summary(terminalreporter):
    """results.md: the table promote.sh posts as PR evidence and the alert quotes."""
    stats = terminalreporter.stats
    rows, n = [], {}
    for outcome in ICON:
        reps = [r for r in stats.get(outcome, []) if getattr(r, "nodeid", "")]
        n[outcome] = len(reps)
        for r in reps:
            note = _reason(r) if outcome in ("failed", "error") else ""
            rows.append(f"| {ICON[outcome]} | `{r.nodeid.removeprefix('qa/')}` | {note} |")
    head = (f"**{n['passed']} passed, {n['failed'] + n['error']} failed, {n['skipped']} skipped** "
            f"in {time.time() - _started:.0f}s against {BASE_URL}")
    table = "\n".join(["| | test | note |", "|---|---|---|", *rows])
    (ARTIFACTS / "results.md").write_text(f"{head}\n\n{table}\n")
