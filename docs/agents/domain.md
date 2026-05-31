# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root — the domain glossary (Marker, DataSource, Dataset, Bbox, bronhouder).
- **`docs/adr/`** — read ADRs that touch the area you're about to work in.
  - `0001-merge-bgt-and-osm-benches.md` — the composite-source / proximity-dedup decision.

If any of these files don't exist, **proceed silently**.

## File structure

Single-context repo:

```
/
├── CONTEXT.md
├── docs/adr/
│   └── 0001-merge-bgt-and-osm-benches.md
└── app/
```

## Use the glossary's vocabulary

When your output names a domain concept (an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md` — `Marker`, `DataSource`, `Dataset`, `Bbox`, `bronhouder`. Don't drift to synonyms.

A new data category (e.g. laadpunten, waterpunten) is a new **Dataset** backed by one or more **DataSource**s — name it that way.

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding.
