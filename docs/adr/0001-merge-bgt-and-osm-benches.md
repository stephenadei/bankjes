# ADR-0001: Merge BGT and OSM benches into one category with proximity dedup

**Status:** Accepted (2026-05-19)
**Decider:** Stephen Adei
**Supersedes:** the implicit invariant in earlier `CONTEXT.md` that *"Each
Dataset has exactly one DataSource"*.

## Context

Bankjes today exposes two filter pills for benches:

- `bench` — DSO BGT-straatmeubilair, filtered to `bronhouder=G0363`,
  ~345 markers (predominantly Weesp).
- `bench_osm` — OSM Overpass `amenity=bench` in the Amsterdam bbox,
  ~6.957 markers (predominantly the centre).

Together they form the "hybrid coverage" pitch in the `/onderzoek`
page: BGT is the official register, OSM fills the visual gap in the
centre. But from a user's perspective the split is **arbitrary**: both
pills represent benches, and tapping both shows two markers per
physical bench wherever they overlap (rare but real, e.g. recent BGT
additions in the centre that are also tagged in OSM).

A user request during the 2026-05-19 grill-with-docs session asked for
"as much as possible one category". Three integration approaches were
considered.

## Decision

**Merge `bench` and `bench_osm` into a single Dataset named `bench`
("Banken") in the public API, deduplicated by spatial proximity.**

Mechanics:

- One filter pill in the UI ("Banken"), not two.
- One Dataset entry in `DATASETS`, with a composite source.
- The composite source fetches both DSO and OSM in parallel,
  deduplicates Markers whose coordinates are within **10 metres** of
  each other, and emits one canonical Marker per physical bench.
- **BGT wins on collision**: when a BGT-marker is within 10m of an
  OSM-marker, the BGT-marker is kept (id + props from BGT) and the OSM
  match is dropped. This preserves the "officiële bron primair"
  narrative and avoids losing the `identificatie` field that the BGT
  marker carries.
- The OSM marker's `backrest` / `material` tags can be attached as
  enrichment to the surviving BGT-marker via a `props.osm_enrichment`
  sub-object, but this is **out of scope for v1** — added later if
  useful.
- The `/onderzoek` gap-analysis page is **kept** and updated to
  reflect the new merged number plus the dedup count ("X BGT, Y OSM,
  Z dedupe-matches, W unique").

The composite source is implemented as a new class in `app/sources.py`
that satisfies the existing `DataSource` Protocol (returns
`list[Marker]`) — so the `Dataset` abstraction itself does not change.
The composition lives **inside** the source, not in the Dataset.

## Consequences

### Positive

- **One mental model**: users see a single "Banken" category instead
  of two competing pills. The civic-tech narrative ("officiële bron
  primair, OSM aanvult") is now an internal implementation detail
  rather than a UI thing the user has to parse.
- **Double-counting solved**: physical benches that appear in both
  registers count as one marker instead of two.
- **Open path for Tafels / Containers**: the same composite-source
  pattern can later be applied to Tafels (BGT + OSM picnic tables) or
  Containers (BGT + OSM trash) without rebuilding the Dataset
  abstraction.

### Negative

- **Dedup heuristic risk**: 10m is empirical, not exact. Two physically
  distinct benches placed close together (e.g. a row of street
  benches) could be falsely merged. Mitigated by the small expected
  overlap region between BGT (Weesp) and OSM (centrum); the false-
  positive surface is narrow.
- **BGT-wins collision rule is opinionated**: drops the OSM marker's
  metadata (notably `backrest`/`material`) unless we later add
  enrichment. For v1 this is acceptable because the data is sparse to
  begin with.
- **`/onderzoek` page needs updating** to explain the dedup logic,
  otherwise the gap-analysis numbers stop making sense.
- **Breaks the CONTEXT.md invariant** that each Dataset has exactly
  one DataSource. The composite-source workaround keeps the *type*
  invariant intact (composite is still a DataSource), but the
  underlying reality is that one Dataset is now backed by two
  registers.

## Rejected alternatives

- **(Visueel-only) Keep both sources separately, merge only the UI
  pill into one toggle**: rejected because it doesn't solve the
  visual double-counting on the map — both markers still render at the
  same location, which is exactly what the user complained about.
- **(Full multi-source Dataset abstraction)**: rejected as
  over-engineering. Generalising `Dataset` to hold a `List[DataSource]`
  would be future-proofing for Tafels/Containers/Afvalbakken
  multi-source merges that may never happen. The composite-source
  pattern delivers the same result with less framework.
- **(Frontend-dedup)**: rejected because it pushes dedup logic into
  Leaflet code where it's harder to test and reason about. Backend
  dedup is unit-testable.

## Implementation outline

```
class MergedBenchSource:
    """DataSource that fetches BGT + OSM in parallel and dedupes."""
    label = "bench"
    name = "Banken"
    color = "#5b7a3f"
    source_type = "merged"
    default_on = True
    featured = True

    def __init__(self, bgt: DsoSource, osm: OsmSource, dedup_m: int = 10):
        self._bgt = bgt
        self._osm = osm
        self._dedup_m = dedup_m

    async def fetch(self, client: httpx.AsyncClient) -> list[Marker]:
        bgt_markers, osm_markers = await asyncio.gather(
            self._bgt.fetch(client), self._osm.fetch(client)
        )
        return _dedup_by_proximity(bgt_markers, osm_markers, self._dedup_m)
```

The dedup helper uses a simple O(n×m) scan (n=BGT≈345, m=OSM≈7000)
which is fast enough at this scale and gets cached for 1h via the
existing TTLCache. A grid-bucket optimisation is unnecessary.

## References

- `CONTEXT.md` — needs an update to soften the "exactly one
  DataSource" claim. The Composite-Source pattern is documented as the
  preferred way to combine registers within one Dataset.
- `app/sources.py` — the new `MergedBenchSource` lands here.
- `app/static/onderzoek.html` — gap-analysis text needs the dedup
  number explained.
