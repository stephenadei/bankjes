# Stephen's Bankjes — domain vocabulary

A civic-tech viewer for Amsterdam street furniture, with an opt-in social
layer on top. Below are the canonical terms the codebase uses; keep them
consistent in commits, comments, and new code.

There are **two parallel domains** in this app — the public civic-tech viewer
and the personal social platform. They share a map surface but their data
models do not mix.

## Public civic-tech domain (anonymous-browsable)

- **Marker** — one geographically-located object from an official or
  community open-data source: `id, lat, lon, props`. Both upstream sources
  reduce their native shapes to this. The map renders one DOM element per
  marker. Markers have **no owner** and live in upstream registers
  (data.amsterdam.nl, OpenStreetMap).
- **DataSource** — anything that, given an HTTP client, returns a list of
  **Markers**. Currently DSO (`api.data.amsterdam.nl/v1`) and OSM Overpass.
  Adding a new one (e.g. PDOK for NL-wide) means writing one DataSource.
  *DataSource yields Markers, not Spots — see Domain boundary below.*
- **Dataset** — the user-visible category for Markers (`Banken`,
  `Picknicktafels`, …). Each Dataset has exactly one DataSource. The
  map's filter pills toggle Datasets on/off.
- **Bbox** — south, west, north, east in WGS84. The Amsterdam bbox is
  reused as the default scope for OSM queries and as the implicit bounds
  for any future `/api/items?bbox=…` filter call.
- **bronhouder** — Dutch term for the BGT-registering authority. `G0363`
  is gemeente Amsterdam. We filter DSO BGT calls on this so neighbouring
  municipalities (G0034 Hilversum, etc.) don't leak into Amsterdam-only
  data.

## Personal social domain (auth-gated)

- **Spot** (NL: *Plekje*) — a user-contributed location that is **not** a
  Marker. Spots have an `owner` (User), a `visibility` (one of `private`,
  `friends`, `public`), and a richer human-facing schema (label,
  description, category, submitter_name). Spots live forever in their own
  layer — they never get promoted to Markers, and Markers never become
  Spots. A "stoel voor de deur" is a Spot; a BGT-registered bench is a
  Marker.
- **User** — anyone who has authenticated via magic-link (passwordless
  email). Identified by stable `user_id`; email is the magic-link target
  and is treated as private.
- **Friendship** — a **symmetric** relationship between two Users:
  `friendships(user_a_id, user_b_id, accepted_at)` with canonical ordering
  (lower id first). Becoming friends requires a request from one side and
  an explicit accept from the other. There is no asymmetric "follow"
  concept.
- **Visibility tier** — every Spot has one of:
  - `private` (default) — only the owner can see it
  - `friends` — owner + all accepted friends of the owner
  - `public` — visible to everyone, **but only after curation** (see Public
    Register)
- **Public Register** — the curated subset of Spots that joins the
  anonymous-browsable civic-tech layer. A Spot does not become `public`
  automatically: the owner submits a request, Stephen (as register
  custodian) approves or denies. Self-published `public` is explicitly
  rejected to protect the civic-tech narrative.

## Domain boundary

Markers and Spots share lat/lon/map-presence but **nothing in the type
system or data layer**:

- A `DataSource` cannot return Spots, and a Spot has no DataSource.
- Spots live in SQLite on the container's mounted volume; Markers live
  upstream (DSO, OSM) and are merely cached in-memory.
- The map renders Markers and Spots in **separate Leaflet layers** with
  distinct toggle controls.
- Spots do not pollute the `/api/items` endpoint. They have their own
  endpoint surface (`/api/spots`).

## Boundaries (operational)

- The **public civic-tech layer** is still **pure proxy** — no DB writes,
  no accounts required, Markers come from upstream every cache miss
  (1 hour TTL since 2026-05-17).
- The **social layer** breaks the prior "no DB" rule: a SQLite database
  in a Docker-mounted volume holds Users, Spots, Friendships, and
  Public-Register entries. Acc and prd each have their own DB file.
- All upstream coordinate reprojection happens server-side at the source:
  DSO is asked for `_format=geojson` so it gives WGS84 (CRS84). We never
  touch RD New (EPSG:28992) ourselves.
- The frontend is **mostly dumb** for the public layer: it fetches
  `/api/datasets` for what to render, `/api/items` for the markers. No
  dataset config in JS source. The social-layer UI does have local
  session state (logged-in cookie).
