# QA and promotion

The "verify on acc", "verify on pre" steps of the deploy flow are automated. A human merges the
release PR into `master` and that is the only manual step left.

## What runs, per env

After every deploy of `develop` (acc) and `pre` (pre), the `qa` job in `.github/workflows/pipeline.yml`
runs `qa/` against the live URL from the VPS runner. acc and pre get the same suite.

| Area | Checked |
|---|---|
| Build | `/healthz` reports the commit just deployed (`version`, from the image's `GIT_SHA`) |
| API | `/healthz`, `/api/datasets` contract, `/api/items` bench set (≥300, unique ids, inside Amsterdam, BGT and OSM both present), bbox filter, 400 on bad input, `/api/coverage` counts, `/api/photos` and `/api/busyness` shape, `/api/route` Dam → Vondelpark on foot (1.5–5 km), wheelchair answers 200 or the documented 503, `/` and `/onderzoek` serve |
| Browser (desktop, Chromium) | page loads, basemap tiles are a real map (not one repeated watermark tile), benches render, BGT and OSM bench pills both non-zero, backrest filter narrows and restores, a dataset pill loads its layer, search "Dam" flies there, nearby list opens a bench popup with "Route hierheen", no JS errors / console errors / failing same-origin requests (`/api/me` 401 for anonymous visitors is expected) |
| Browser (mobile, Pixel 7) | loads, markers and the bottom sheet show, no errors |

Screenshots (`desktop-home`, `desktop-search`, `desktop-detail`, `mobile-home`, plus `fail-<test>` for
any failure) and `results.md` are uploaded as the run's `qa-<env>-<sha>` artifact (30 days).

Run it by hand against any env:

```bash
python3 -m venv /tmp/qa && /tmp/qa/bin/pip install -r qa/requirements.txt
/tmp/qa/bin/python -m playwright install --only-shell chromium
QA_BASE_URL=https://bankjes-acc.stephensprive.app /tmp/qa/bin/pytest qa -q
```

## How promotion works

1. Feature PR into `develop`, merge. The push deploys **acc**, then QA runs on acc.
2. acc green: `scripts/promote.sh acc` merges that commit, plus `master`, into `pre`. This is a
   fast-forward when nothing diverged. The evidence goes as a comment on the feature PR.
3. The push to `pre` deploys **pre**, then QA runs on pre.
4. pre green: `scripts/promote.sh pre` opens the release PR `pre → master`, or comments on the one already
   open. Each green pre run adds an `## Evidence` comment with results and screenshot links. It also posts
   one line to herald `personal.log`.
5. You merge the release PR with **Create a merge commit**. That push deploys **prd**.

Red at any step: nothing is promoted and herald `ops.alert` posts one message with the run link. That
covers a failed QA test, a failed install and a merge conflict. Fix forward on `develop`, or rerun in
place (`gh run rerun <id> --failed`) when an upstream (Overpass, DSO, OSRM) was the cause.

An Overpass outage shows up as "one register missing" plus the browser checks that depend on it. The
bench merge then serves BGT only and caches that for the hour (`CACHE_TTL_SECONDS`). A rerun only goes
green once the env has refetched, which means after the TTL or a container restart.

Why it is built this way:

- Pushes and PRs use the runner's stephenadei gh login. A `GITHUB_TOKEN` push would not start the pre
  pipeline, and a `GITHUB_TOKEN` PR would never get `master`'s required `test` check. This repo also does
  not let Actions open PRs.
- `master` is merged into `pre` so the release PR is never "behind" under `master`'s strict
  up-to-date protection, and so pre is never behind prd.
- The release PR carries `no-automerge`. Without it, `personal-pr-automerge` would squash-merge it
  after 1h green and delete its head branch, which is `pre`.

## Still a human

- **Merging to prd.** This stays a deliberate decision. Branch protection (PR + `test`) is unchanged.
- **Judgement calls.** Copy, look and feel. The screenshots are there so you can check them without
  opening the site.
- **Not covered:** live turn-by-turn with real GPS, magic-link login and `/admin`, the `/onderzoek`
  charts beyond the page being served, and prd itself, which serves coming-soon while `APP_ENV=prd`.
