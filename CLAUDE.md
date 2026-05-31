# CLAUDE.md — Stephen's Bankjes

Civic-tech viewer for Amsterdam street furniture (benches). FastAPI + httpx +
cachetools backend, vanilla JS + Leaflet frontend. Pure proxy, no DB.
See `README.md` for the stack and `CONTEXT.md` for domain vocabulary.

## ⚠️ Git account

Personal repo (`stephenadei/bankjes`). The maintainer is sometimes signed in to
a work account (`stephenatohpen`) in the same shell. **Verify the active `gh`
account is `stephenadei` before any `gh` or `git push` operation** — see
`docs/agents/issue-tracker.md` for the guard.

## Agent skills

### Issue tracker

Issues live as GitHub issues on `stephenadei/bankjes` (via `gh`). See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical role names equal the label strings; category roles map to `bug` / `enhancement`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
