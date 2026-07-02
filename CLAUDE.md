# CLAUDE.md — Stephen's Bankjes

Civic-tech viewer for Amsterdam street furniture (benches). FastAPI + httpx +
cachetools backend, vanilla JS + Leaflet frontend. Pure proxy, no DB.
See `README.md` for the stack and `CONTEXT.md` for domain vocabulary.

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
