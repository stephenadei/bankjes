# Own navigation platform — design

**Status:** ACTIVE
**Datum:** 2026-07-02
**Sub-project:** 1 van 4 (routing/navigatie) — zie roadmap onderaan

## Doel

Vervang de "↗ Open in Maps"-uitstap naar Google door **eigen in-app navigatie**:
route + afstand/ETA + live turn-by-turn naar een bankje, voor **lopen, fietsen
en rolstoel**. Onafhankelijk van Google; open-source engines via hosted API's
(zelf-hosten kan later zonder frontend-wijziging).

## Beslissingen (met Stephen doorgenomen)

| Vraag | Keuze |
|---|---|
| Scope | Alles, gefaseerd — dit is fase 1 (routing) |
| Onafhankelijkheidslat | Open hosted API's (geen eigen infra nu; engines zijn self-hostable) |
| Nav-diepte | **Live turn-by-turn** (GPS-volgen, stap-advance, reroute, spraak) |
| Modi | 🚶 lopen · 🚲 fietsen · ♿ rolstoel (on-mission: banken dienen precies wie toegankelijke routes nodig heeft) |
| Engine | **OpenRouteService** — enige met een volwaardig wheelchair-profiel (foot-walking / cycling-regular / wheelchair); 2000 req/dag gratis |

Geocoding blijft **PDOK** (al onafhankelijk); tiles blijven CARTO (fase 3);
Street View-link blijft tot fase 2 (Mapillary; token al aanwezig in backend).

## Architectuur

**Backend proxied + normaliseert; frontend draait de live-loop.** ORS-key
blijft server-side; het antwoord wordt genormaliseerd naar een eigen contract
zodat de engine later inwisselbaar is (self-hosted ORS/Valhalla) zonder
frontend-aanpassing. Alleen de eerste route + reroutes raken de API — het
volgen zelf is client-side geometrie.

```
GET /api/route?from_lat&from_lon&to_lat&to_lon&mode=foot|bike|wheelchair
  → mode → ORS-profiel · POST /v2/directions/{profile}/geojson (language=nl)
  → genormaliseerd: { geometry:[[lat,lon]…], distance_m, duration_s,
                      steps:[{instruction, distance_m, duration_s,
                              maneuver_point, geometry_idx, type}] }
  → TTL-cache (cached_fetch-patroon, zoals /api/photos)
```

Guards (trust boundary — de key is publiek bereikbaar via dit endpoint):
- coördinaten moeten binnen ~50 km van Amsterdam liggen (anders 400) — het
  endpoint is geen gratis wereld-router;
- daglimiet (1500, onder ORS' 2000) → 429;
- **keyless fallback-engine**: zonder `ORS_API_KEY` routeert het endpoint via
  FOSSGIS-OSRM (`routing.openstreetmap.de`, dezelfde open instances als
  osm.org; identificerende User-Agent, zelfde dagbudget) met Nederlandse
  instructie-synthese — lopen/fietsen werken out-of-the-box, ORS voegt het
  rolstoelprofiel toe (♿ zonder key → 503 met uitleg; nooit stilletjes een
  looproute als rolstoelroute serveren). ORS stuk → 503; frontend toont
  OSM-directions-fallback-link.

## Live-nav (frontend, vanilla JS in index.html)

States: `idle → preview → navigating → arrived`.

- **Preview** (na "Route" in de popup): polyline + fitBounds, modus-toggle,
  "420 m · 5 min", uitklapbare stappenlijst, Start. Zonder locatie: route
  vanaf kaartmidden, geen Start.
- **Navigating**: `watchPosition` (high accuracy) → puck; per fix (géén API):
  projectie op routegeometrie (windowed nearest-segment), stap-advance binnen
  ~20 m van maneuver_point + spraak (`speechSynthesis`, nl-NL, mute-toggle,
  voorkeur in localStorage), resterende afstand/ETA uit cumulatieve afstanden,
  off-route >40 m gedurende 3 fixes → één reroute-call (≥10 s tussen reroutes),
  Wake Lock aan (heraanvraag bij visibilitychange), kaart volgt tenzij de
  gebruiker recent zelf pande (8 s).
- **Arrived**: binnen ~15 m van het bankje → "Je bent er".

Google-verwijzingen: `google.com/maps/search` (popup + admin) **weg**;
admin krijgt een OSM-link. Street View blijft (fase 2).

## Tests (repo-stijl: hermetisch, MockTransport)

- normalisatie ORS-fixture → contract; bounds-validatie; budget-guard;
- endpoint: happy path, geen key → 503, buiten NL → 400, upstream-fout → 503
  (fallback niet gecached);
- HTML-asserts: nav-UI aanwezig, `google.com/maps/search` afwezig,
  wheelchair-modus aanwezig, watchPosition aanwezig.

## Roadmap

1. **Routing/nav — dit document. GELEVERD** (PR #26 + follow-up).
2. Street View → Mapillary. **GELEVERD** (popuplink "Straatbeeld" →
   mapillary.com; de foto's kwamen er al vandaan).
3. Tiles: CARTO ≠ Google en valt binnen de gekozen lat ("open hosted");
   wissel naar open/pmtiles blijft optioneel vervolgwerk.
4. Fonts self-hosten. **GELEVERD** (`app/static/fonts/`, latin-subset
   variable woff2, OFL; nul `google.*`-requests in de hele app).
