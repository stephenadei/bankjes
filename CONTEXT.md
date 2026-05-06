# Stephen's Bankjes — domain vocabulary

Small civic-tech viewer for Amsterdam street furniture. The vocabulary below
is what the codebase uses; keep using it consistently in commits, comments,
and any new code.

## Core terms

- **Marker** — one geographically-located object: `id, lat, lon, props`. Both
  data sources reduce their native shapes to this. The map renders one DOM
  element per marker.
- **DataSource** — anything that, given an HTTP client, returns a list of
  Markers. Currently DSO (`api.data.amsterdam.nl/v1`) and OSM Overpass.
  Adding a new one (e.g. PDOK for NL-wide) means writing one DataSource.
- **Dataset** — the user-visible category (`Banken`, `Picknicktafels`,
  ...). Each Dataset has exactly one DataSource. The map's filter pills
  toggle Datasets on/off.
- **Bbox** — south, west, north, east in WGS84. The Amsterdam bbox is
  reused as the default scope for OSM queries and as the implicit bounds
  for any future `/api/items?bbox=…` filter call.
- **bronhouder** — Dutch term for the BGT-registering authority. `G0363`
  is gemeente Amsterdam. We filter DSO BGT calls on this so neighbouring
  municipalities (G0034 Hilversum, etc.) don't leak into Amsterdam-only
  data.

## Boundaries

- The app is **pure proxy** — no DB, no persistence, no user accounts.
  Markers come from upstream every cache miss (5min TTL).
- All upstream coordinate reprojection happens server-side at the source:
  DSO is asked for `_format=geojson` so it gives WGS84 (CRS84). We never
  touch RD New (EPSG:28992) ourselves.
- The frontend is **dumb**: it fetches `/api/datasets` for what to render,
  `/api/items` for the markers. No dataset config in JS source.
