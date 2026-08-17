# CLAUDE.md — Stephen's Bankjes

**Laatst geverifieerd:** 2026-08-17

Civic-tech viewer for Amsterdam street furniture (benches). FastAPI + httpx +
cachetools backend, vanilla JS + Leaflet frontend.
See `README.md` for the stack and `CONTEXT.md` for domain vocabulary.

**No longer a pure proxy.** This file claimed "Pure proxy, no DB" until
2026-08-17; `app/db.py` uses `aiosqlite` with migrations under `app/migrations/`,
and `app/spots_repo.py` persists spots. Upstream fetches are still proxied and
cached (`app/cached_fetch.py`) — the DB is additive, not a replacement.

## Commands

```bash
python3 -m pytest              # asyncio_mode=auto, testpaths=tests (pyproject.toml)
python3 -m uvicorn app.main:app --reload
scripts/deploy.sh              # promotes through the branch->env chain below
python3 scripts/generate-assets.py
```

## Architecture

- `app/` — FastAPI application: `main.py` (entrypoint), `routing.py`, `admin.py`,
  `auth.py`, `domain.py`, `sources.py`, `spots.py`
- `app/db.py` + `app/migrations/` — aiosqlite persistence and schema migrations
- `app/cached_fetch.py` — cachetools-backed upstream proxy
- `app/static/` — vanilla JS + Leaflet frontend
- `scripts/` — `deploy.sh`, `generate-assets.py`
- `tests/` — pytest suite (`test_admin`, `test_api`, `test_auth`, `test_busyness`, …)
- `docs/` — `adr/`, `agents/`, `specs/`
- `data/` — runtime SQLite (`bankjes.db` + `-wal`/`-shm`). Absent in this repo and
  created per environment, so it exists in `bankjes-acc/`, `bankjes-pre/` and
  `bankjes-prd/` but not in a fresh clone. Never commit it.

One CLAUDE.md serves four checkouts: this repo plus the three env directories, which
are the same repo on `develop`/`pre`/`master`. Edit it here and let the promote chain
carry it — hand-editing `projects/bankjes-{acc,pre,prd}/CLAUDE.md` is overwritten by
the next deploy.

## ⚠️ Git account

Personal repo (`stephenadei/bankjes`). The maintainer is sometimes signed in to
a work account (`stephenatohpen`) in the same shell. **Verify the active `gh`
account is `stephenadei` before any `gh` or `git push` operation** — see
`docs/agents/issue-tracker.md` for the guard.

## Deploy flow — promote through the chain, never straight to prd

This repo uses the ADR-0009 bankjes-pattern. The CD pipeline maps **branch → env**:

| Branch | Env | Dir |
|--------|-----|-----|
| `develop` | acc | `projects/bankjes-acc/` |
| `pre` | pre | `projects/bankjes-pre/` |
| `master` | **prd** | `projects/bankjes-prd/` |

A push to a branch deploys *that* env directly — there is no automatic
promotion. So **`master` = production**. Default flow for any change:

1. Feature branch → PR into **`develop`** → merge → verify on **acc**.
2. Fast-forward / PR **`pre`** to develop's commit → verify on **pre**.
3. Fast-forward / PR **`master`** to pre's commit → prd.

Do **not** base feature PRs on `master` (that ships straight to prd, skipping
the acc/pre buffer — the whole reason the pattern exists, born from a prd-down
incident). `master` is branch-protected (PR + `test` check required); the
acc→pre→prd *ordering* is convention — follow it. Keep acc/pre at or ahead of
prd, never behind.

## Agent skills

### Issue tracker

Issues live as GitHub issues on `stephenadei/bankjes` (via `gh`). See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical role names equal the label strings; category roles map to `bug` / `enhancement`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
