# ADR-0001: Add a social layer on top of the civic-tech viewer

**Status:** Proposed (2026-05-19)
**Decider:** Stephen Adei

## Context

Bankjes shipped as a **pure-proxy civic-tech viewer**: no DB, no
persistence, no accounts. The map shows BGT (data.amsterdam.nl) + OSM
markers; visitors browse anonymously. The original `CONTEXT.md` made
this explicit ("pure proxy — no DB, no persistence, no user accounts").

A user request surfaced during a casual link-share: someone wanted to
contribute a personal piece of street furniture ("een stoel voor de
deur") and asked if it could be included. Probing that single request
revealed a much broader product question — should Bankjes accept user
contributions, and if so, how?

The natural narrow answer (anonymous public submissions with light
moderation) was considered but rejected in favour of a richer product:
a personal collection per user, with three visibility tiers (private,
friends, public), symmetric friendships, and a curated public register.

This re-frames Bankjes from a one-shot civic-tech viewer into a hybrid:
a public-by-default civic-tech surface *with an opt-in social platform
layered on top*.

## Decision

Bankjes becomes a **dual-domain application**:

1. The existing **civic-tech viewer** (Markers from DSO + OSM) stays
   exactly as it is — anonymous, no auth, no DB writes, accessible to
   logged-out visitors. This is non-negotiable: the portfolio narrative
   ("burger laat zien wat 'r aan straatmeubilair staat") depends on
   anonymous browsability.

2. A new **social layer** introduces:
   - **Users**, authenticated by magic-link (passwordless email)
   - **Spots** (NL: *Plekjes*), user-contributed locations that are
     categorically separate from Markers — they have an owner, a
     visibility, and a richer schema; they never get promoted to Markers
   - **Friendships**, symmetric (request + accept on both sides)
   - **Visibility tiers**: `private` (default), `friends`, `public`
   - A **curated public register** — `public` visibility is requested by
     the owner and approved by the maintainer (Stephen). Self-publishing
     to the civic-tech surface is explicitly rejected
   - **SQLite** in a Docker-mounted volume as the persistence layer for
     the social domain; the civic-tech layer remains DB-less

3. The two domains share a map surface but **nothing in the type
   system**: a `DataSource` cannot return a `Spot`, a `Spot` has no
   `DataSource`, and Spots are rendered in their own Leaflet layer
   parallel to (not merged with) the Marker layers.

## Consequences

### Positive

- **Civic-tech narrative preserved** — anonymous visitors continue to see
  exactly the BGT+OSM surface that defined the project from day one. The
  social features layer adds, never subtracts.
- **Privacy by default** — Spots start private; explicit owner action
  required to share. Avoids the common social-app failure mode of
  accidental over-share.
- **Type-system safety** — keeping Markers and Spots as distinct types
  means a misconfigured ACL query can leak at most one category, not
  contaminate the public civic-tech layer.
- **Bottleneck protection for the public register** — Stephen as curator
  prevents the public layer from filling with junk submissions,
  preserving portfolio quality.

### Negative

- **Architectural complexity** — the prior "single proxy with TTL cache"
  shape becomes "proxy + DB + auth + session + ACL + curation queue".
  Maintenance burden grows.
- **One-way door on infra** — adding persistence brings backup needs,
  schema migration discipline, volume-mount discipline. Removing all
  this later (if the social layer underperforms) means dropping all
  user data.
- **Curator bottleneck** — the public register is gated on Stephen
  reviewing requests. At ~10–100 submissions/year this is trivial, but
  if usage spikes the curation backlog could lag visibly.
- **Surface-area shift in portfolio narrative** — Bankjes is no longer
  *only* a civic-tech viewer. Recruiters and reviewers must understand
  the dual nature; weak framing could read as scope creep.

## Rejected alternatives

- **(N) Status quo**: keep Bankjes pure-proxy, decline user contributions
  entirely. Rejected because it forfeits the engagement signal the
  feature request represents.
- **(A) Anonymous public submissions** (no accounts, honeypot +
  IP-limit): considered earlier in the same session; rejected when the
  product expanded to include privacy tiers and friendships — anonymous
  orphan spots don't fit a model where every spot has an owner with a
  visibility choice.
- **(P2) Login-required for everything**: rejected because it would
  break the link-share UX (e.g. Paul forwarding the URL in iMessage
  without expecting a login wall) and erode the civic-tech narrative.
- **(B) Asymmetric (Twitter-style) friendships**: rejected because the
  intimate-scale "Bankjes is for me and people I know" semantics don't
  match a broadcast follow model.
- **(C) Group/Circles-based friendships**: rejected as over-engineered
  for the expected scale.
- **(Self-publish) public register**: rejected because the word
  *register* implies curation, and uncurated public submissions would
  pollute the civic-tech layer that is the portfolio's keystone.

## References

- `CONTEXT.md` (this commit) — updated vocabulary reflecting the
  two-domain split.
- Implementation plan: forthcoming — this ADR locks the strategic
  decisions, a concrete spec + plan will follow once the remaining
  detail-level grilling completes (default visibility on submit,
  identity privacy on public layer, friend-request UX, DB schema, API
  surface, onboarding flow).
- Earlier aesthetic-pass spec
  (`docs/specs/active/2026-05-18-bankjes-aesthetic-design.md` in the
  workspace monorepo) is **unaffected** by this decision — it ships
  independently to acc and prd.
