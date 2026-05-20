# Stephen's Bankjes — domain vocabulary

A civic-tech viewer for Amsterdam street furniture. The vocabulary below
is what the codebase uses; keep it consistent in commits, comments, and
any new code.

## Core terms

- **Marker** — one geographically-located object from an official or
  community open-data source: `id, lat, lon, props`. Both upstream
  sources reduce their native shapes to this. The map renders one DOM
  element per marker. Markers have no owner and live in upstream
  registers (data.amsterdam.nl, OpenStreetMap).
- **DataSource** — anything that, given an HTTP client, returns a list
  of `Marker`s. Currently DSO (`api.data.amsterdam.nl/v1`) and OSM
  Overpass. Adding a new one (e.g. PDOK for NL-wide) means writing one
  DataSource. The composite-source pattern (see ADR-0001) lets one
  Dataset combine two registers if needed.
- **Dataset** — the user-visible category for Markers (`Banken`,
  `Picknicktafels`, …). The map's filter pills toggle Datasets on/off.
  `Banken` is backed by a composite source that merges BGT + OSM with
  proximity deduplication; the rest are single-source.
- **Bbox** — south, west, north, east in WGS84. The Amsterdam bbox is
  the default scope for OSM queries and the implicit bounds for any
  `/api/items?bbox=…` filter call.
- **bronhouder** — Dutch term for the BGT-registering authority.
  `G0363` is gemeente Amsterdam. We filter DSO BGT calls on this so
  neighbouring municipalities don't leak into Amsterdam-only data.

## Boundaries

- The app is **pure proxy** — no DB, no persistence, no user accounts.
  Markers come from upstream every cache miss (1 hour TTL).
- All upstream coordinate reprojection happens server-side at the
  source: DSO is asked for `_format=geojson` so it gives WGS84 (CRS84).
  We never touch RD New (EPSG:28992) ourselves.
- The frontend is dumb: it fetches `/api/datasets` for what to render
  and `/api/items` for the markers. No dataset config in JS source.
- A new bench-photo endpoint (`/api/photos`) proxies Mapillary's
  street-level imagery so the marker popups can show what the area
  looks like; same proxy + TTL-cache shape as the main `/api/items`
  flow, no DB.
