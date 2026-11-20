# Bankjes for iPhone: native SwiftUI app (v1)

**Status:** APPROVED (Stephen, 2026-11-20): D1, D2 and D3 as recommended. Signing corrected after approval, see the Signing row.
**Date:** 2026-11-20
**Repo:** `stephenadei/bankjes`. The app lives in `ios/`; backend changes go to `app/`.
**Builds on:** `docs/specs/2026-07-02-own-navigation-design.md` (the `/api/route` contract and the live-nav loop)

## Goal

A native iPhone app for Stephen's Bankjes, distributed privately through TestFlight (Stephen plus invited friends). v1 does three things:

1. **Map.** All bench Markers (Dataset `bench`, the merged BGT+OSM register, ADR-0001) on MapKit with clustering, plus a "near me" list.
2. **Navigation.** A route and live turn-by-turn directions to a bench, walking, cycling or by wheelchair, with the same behaviour as the web app.
3. **Accounts and own Spots.** Sign in by magic link; list, add, edit and delete your own Spots (Plekjes); request public listing or revoke it.

Not in v1: Mapillary photos (`/api/photos`), busyness (`/api/busyness`), bench detail extras, other Datasets (Tafels, Containers, Afvalbakken, Laadpunten, Waterpunten), admin moderation, `/onderzoek`.

## Decisions already taken (fixed)

| Question | Decision |
|---|---|
| Stack | Native SwiftUI + MapKit against the existing FastAPI backend; no new backend service |
| Distribution | Private TestFlight only, Apple team `QQS3VCWWUJ` |
| Code location | `ios/` folder in the bankjes repo; feature branches → `develop` like every other change |
| v1 scope | Map + clusters + near me; navigation (foot/bike/wheelchair); auth + Spots CRUD + request/revoke public |

## Findings that shape the design

- **The API on prd works.** `APP_ENV=prd` gates only `/` and `/onderzoek` (`app/main.py:_should_serve_coming_soon`). `https://bankjes.stephenadei.nl/healthz` and `/api/items?dataset=bench` both return 200 on prd. The prd host is `bankjes.stephenadei.nl` (`.env.prd.example` `APP_BASE_URL`); acc and pre are `bankjes-{acc,pre}.stephensprive.app`.
- **Payload.** `GET /api/items?dataset=bench` returns 7,741 markers: **1.35 MB raw and 131 KB gzipped** (measured on acc on 2026-11-20). `GZipMiddleware` is on, and URLSession sends `Accept-Encoding: gzip` by default. 131 KB once per launch is fine on a phone. The response has no `Cache-Control`, `ETag` or `Last-Modified` header, and Cloudflare reports `DYNAMIC`. `?bbox=` exists, but it only filters the server's whole-Amsterdam cache, so per-pan bbox calls would add requests without saving upstream work. **Decision: no backend items change.** The app fetches `dataset=bench` once, keeps the last good response on disk, and filters and sorts on the device.
- **Item shape.** `{count, items:[{id, lat, lon, dataset, props}]}`. `props` is raw: BGT markers carry the full BGT record, and OSM markers carry their tags plus `source_type`. The app decodes only `id`, `lat`, `lon`, `props.source_type` and `props.backrest`, and ignores the rest.
- **Auth today.** `app/auth.py`. The magic token is `URLSafeTimedSerializer(SECRET_KEY, salt="magic-link")`, has a 30-minute TTL and is stored in `magic_link_tokens`; it is single-use and a new request supersedes it. `/auth/verify` consumes the token, upserts the user and sets the `bankjes_session` cookie. That cookie holds `URLSafeTimedSerializer(SECRET_KEY, salt="session").dumps({user_id, issued_at})` with a 30-day TTL. It is stateless: there is no session table, and logout only deletes the cookie. `get_current_user` reads only the cookie. **The same signed session string can be accepted as `Authorization: Bearer` without any new crypto.**
- **Routing.** `/api/route` already returns an engine-agnostic contract: `geometry [[lat,lon]…]`, `distance_m`, `duration_s` and `steps[{instruction (Dutch), distance_m, duration_s, maneuver_point, geometry_idx, type}]`. The engine is ORS when `ORS_API_KEY` is set; without it, foot and bike fall back to keyless FOSSGIS-OSRM and wheelchair returns 503. Guards: coordinates within 50 km of Amsterdam (otherwise 400), a daily budget of 1,500 (otherwise 429), a 10-minute TTL cache keyed on coordinates rounded to 4 decimals. The live loop runs entirely on the client (`app/static/index.html` `navOnFix`): windowed nearest-point search (curIdx −5…+60), step advance within 20 m on foot or by wheelchair and 30 m by bike (or once `geometry_idx` is passed), off-route when more than 40 m away for 3 fixes, then a reroute at most once every 10 s, arrival within 15 m, and Dutch speech.
- **nginx needs no change.** Every vhost proxies `location /` to the app (`/etc/nginx/sites-enabled/bankjes*`), so `/.well-known/apple-app-site-association` can be a FastAPI route, and no sudo is needed.
- **Side finding (out of scope, file an issue).** `_cached_fetch` (`app/main.py`) caches a *degraded* `MergedBenchSource` result for the full hour. When Overpass blips, the map shows only the 345 BGT benches for 60 minutes. Prd was in exactly that state while this spec was written: `count=345`, while `/api/coverage` on pre reported 7,741. The same cache feeds the app.

## API contract the app uses

All paths are relative to the env base URL. Auth "opt" means the response depends on the caller; "req" means it returns 401 without a session.

| # | Method | Path | Request | Response | Auth | Exists? |
|---|---|---|---|---|---|---|
| 1 | GET | `/api/items?dataset=bench` | – | `{count, items:[{id, lat, lon, dataset, props}]}` (502 if the bench upstream fails completely) | none | yes |
| 2 | GET | `/api/route` | `from_lat, from_lon, to_lat, to_lon, mode=foot\|bike\|wheelchair` | route contract above; 400 outside the service area, 429 when the budget is spent, 503 when the route is unavailable or there is no ORS key for wheelchair | none | yes |
| 3 | POST | `/api/auth/request-magic-link` | `{email, client?: "ios"}` | `{sent: true}`; 400 for a bad email | none | **extend** (`client`) |
| 4 | GET | `/auth/app?token=` | – | Universal Link target. With the app installed, iOS opens the app and the request never reaches the server. Without it, a 302 to `/auth/verify?token=…` (web fallback) | none | **new** |
| 5 | POST | `/api/auth/token` | `{token}` (magic token) | `{session, user:{id, email, display_name, is_admin}}`; 400/410 like verify; **no Set-Cookie** | none | **new** |
| 6 | GET | `/api/me` | – | `{id, email, display_name, is_admin}` | req | yes (bearer via the shared dependency) |
| 7 | GET | `/api/spots` | – | `{spots:[Spot]}`: public+approved Spots, plus all of your own | opt | yes |
| 8 | POST | `/api/spots` | `{lat, lon, label(1–60), description?(≤400), category?}`. Category is one of `bank, stoel, picknicktafel, krukje, anders` | Spot | req | yes |
| 9 | PATCH | `/api/spots/{id}` | `{label?, description?, category?}` | Spot; 403 if not yours | req | yes |
| 10 | DELETE | `/api/spots/{id}` | – | `{ok: true}` | req | yes |
| 11 | POST | `/api/spots/{id}/request-public` | – | Spot (`visibility=public`, `public_status=requested`); 409 if already approved | req | yes |
| 12 | POST | `/api/spots/{id}/revoke-public` | – | Spot (`visibility=private`, `public_status=revoked`) | req | yes |
| 13 | GET | `/.well-known/apple-app-site-association` | – | AASA JSON, `application/json`, no redirect | none | **new** |

Spot = `{id, lat, lon, label, description, category, visibility, public_status, created_at, owner:{id, display_name}}`. `GET /api/spots/{id}` exists, but v1 does not need it because the list carries everything.

Logout in the app means deleting the token from the Keychain. `POST /api/auth/logout` only clears a cookie, so the app does not call it.

## Auth design (smallest backend change)

**Flow.** The app sends `POST /api/auth/request-magic-link {email, client:"ios"}`. The server emails `{APP_BASE_URL}/auth/app?token=…`, iOS opens the app through the Universal Link, and `.onOpenURL` passes the token to the app. The app calls `POST /api/auth/token`, receives `session`, stores it in the Keychain (`kSecAttrAccessibleAfterFirstUnlock`), and sends `Authorization: Bearer <session>` on every request.

**Why a separate `/auth/app` path, not `/auth/verify`.** If the AASA claimed `/auth/verify`, every magic link opened on that iPhone would launch the app, including when the user is trying to sign in to the website in Safari. `/auth/app` is claimed only by links that the app itself requested. If the app is missing, `/auth/app` 302s to `/auth/verify`, so the link still signs the user in on the web.

**Backend diff sketch** (all in `app/auth.py` plus one route in `app/main.py`):

```python
# app/auth.py
class MagicLinkRequest(BaseModel):
    email: str
    client: Optional[str] = None            # "ios" → link opens the app

# request_magic_link:
path = "/auth/app" if payload.client == "ios" else "/auth/verify"
link = f"{base}{path}?token={token}"

async def _consume_magic_token(db, token: str) -> str:
    """Body of verify_magic_link, extracted: signature/age, DB row, consume, upsert. Returns user_id."""
    ...  # unchanged logic, same HTTPExceptions (400/410)

@router.get("/auth/verify")              # now: user_id = await _consume_magic_token(...); redirect + cookie
@router.get("/auth/app")                 # reached only without the app installed
async def app_link_fallback(token: str):
    return RedirectResponse(f"/auth/verify?token={quote(token)}", status_code=302)

class TokenExchange(BaseModel):
    token: str

@router.post("/api/auth/token")
async def exchange_token(payload: TokenExchange, request: Request):
    user_id = await _consume_magic_token(request.app.state.db, payload.token)
    session = _session_serializer().dumps({"user_id": user_id, "issued_at": _now_utc().isoformat()})
    user = await _load_user(request.app.state.db, user_id)     # extracted from get_current_user
    return {"session": session, "user": user.model_dump()}

# get_current_user: one line changes where the token comes from
auth = request.headers.get("authorization", "")
token = auth[7:] if auth[:7].lower() == "bearer " else request.cookies.get(SESSION_COOKIE_NAME)
```

```python
# app/main.py: AASA. APPLE_APP_ID is a module constant (one bundle, one team), not env config.
APPLE_APP_ID = "QQS3VCWWUJ.app.stephensprive.bankjes"

@app.get("/.well-known/apple-app-site-association", include_in_schema=False)
async def aasa():
    return JSONResponse({"applinks": {"details": [
        {"appIDs": [APPLE_APP_ID], "components": [{"/": "/auth/app", "comment": "magic link → app"}]}
    ]}})
```

Every env serves the same AASA. The entitlement decides which hosts the app claims.

**Tests** (`tests/test_auth.py`, existing `client_with_envs` style):
- `client:"ios"` produces an `/auth/app` link (assert on the mocked Resend payload);
- `/api/auth/token` returns a session, and `/api/me` with `Authorization: Bearer` returns 200;
- replaying the token returns 410;
- an exchange response carries no `set-cookie` header;
- a bad bearer token is treated as unauthenticated (401);
- `/auth/app` 302s to `/auth/verify`;
- the AASA returns 200 with `application/json` and the expected `appIDs`.

**Security notes.**
- **CSRF.** Bearer tokens are never attached by a browser, so the bearer path adds no CSRF surface. The cookie path is unchanged (`SameSite=Lax`). The exchange endpoint must not set a cookie: URLSession would otherwise store it in `HTTPCookieStorage` and the app would end up with two credentials. The app also sets `httpShouldSetCookies = false`.
- **Token lifetime.** The bearer token is the same 30-day stateless session as the web cookie, with the same revocation story: there is none, apart from rotating `SECRET_KEY`. When the token expires (401), the app returns to the sign-in screen. No refresh endpoint in v1. Add a sliding refresh if 30-day re-logins annoy testers.
- **Environment mismatch.** The magic link carries the server's `APP_BASE_URL` host. If the link host differs from the app's configured API base (for example an acc email opened by a prd build), the app shows "deze link hoort bij een andere omgeving" instead of a confusing 400.
- **Unchanged and out of scope.** `request-magic-link` has no rate limit today, and that stays as it is.

## Navigation design

**Recommendation: use `/api/route` (ORS/OSRM) for all three modes and port the web app's live loop to Swift.** Do not use MKDirections.

Reasons:
1. **One engine and one contract.** Wheelchair can only come from ORS. Mixing MKDirections for foot and bike with ORS for wheelchair means two route shapes and two step vocabularies feeding one guidance loop, and routes that differ from the website for the same bench.
2. **MKDirections does not remove the work.** It returns a polyline and steps but no guidance engine, so a follow-the-route loop is needed either way. It has no wheelchair profile, and cycling directions are not available to a third-party app at our iOS 17 target. The hard part, the loop, is identical in both cases, and a reference implementation already exists in `index.html`.
3. **Already tuned and tested.** The thresholds (advance 20/30/20 m, off-route 40 m × 3 fixes, reroute at most every 10 s, arrival 15 m) and the Dutch instructions come straight from the web app, so behaviour matches.
4. **Cost.** Each route or reroute is one budgeted call. A handful of TestFlight users is negligible against 1,500 per day.

Accepted downside: a route needs the network. Mid-route the loop needs no calls, so a dead zone only blocks reroutes.

**iOS shape.**
- `CLLocationManager`: `desiredAccuracy = kCLLocationAccuracyBest` and `activityType = .fitness`, started only in the navigating state.
- The route is drawn as an `MKPolyline` overlay.
- `RouteFollower` is a pure struct in `BankjesCore`: `(route, mode, fix) → {stepIdx, curIdx, remaining m/s, event: advance(instruction) | offRoute | reroute | arrived}`. It is a direct port of `navNearestOnRoute`, `navOnFix` and `navRemaining`.
- Speech: `AVSpeechSynthesizer` with voice `nl-NL`, plus a mute toggle stored in `UserDefaults`.
- `UIApplication.isIdleTimerDisabled = true` while navigating (the Wake Lock equivalent).
- The map follows the user unless they panned in the last 8 s.
- States: `idle → preview → navigating → arrived`. Preview shows the polyline, distance and ETA, a mode picker and the step list. Without a location fix there is no Start button, as on the web.
- Errors: a 503 on wheelchair shows the server's `detail` text. On any other 503 or 429, show the error and offer "Open in Kaarten" (`MKMapItem.openInMaps` with walking or cycling) as the escape hatch.

## Privacy and permissions

- `NSLocationWhenInUseUsageDescription`: "Bankjes gebruikt je locatie om bankjes bij jou in de buurt te tonen en je ernaartoe te navigeren. Je locatie wordt alleen gedeeld om een route te berekenen."
- If decision D2 (navigation with the screen locked) is accepted, add `UIBackgroundModes: [location]` and set `allowsBackgroundLocationUpdates = true` only while navigating. That still uses When-In-Use authorization (iOS shows the blue indicator), so "Always" is never requested.
- **What leaves the phone.**
  - "Near me" sorting runs on the device and sends nothing.
  - Location goes to the server **only** as `from_lat/from_lon` on `/api/route` (the first route and each reroute). The server forwards it to ORS or OSRM, keeps it up to 10 minutes in the route cache (rounded to about 10 m), and uvicorn's default access log records the full query string, coordinates included. The permission text above is honest about this. Dropping query strings from the access log is a one-line follow-up if Stephen wants it; it is not needed for v1.
  - Adding a Spot sends the Spot's coordinates. By default that is the map centre or a long-press point, not a live fix.
- **Offline / no network.**
  - Map: show the last cached `items.json` (Caches directory) with a "laatst bijgewerkt …" banner. Only the very first launch with no network shows an empty state.
  - Near me: works offline from the cache.
  - Route: shows an error with a retry. An active navigation keeps guiding offline; only reroutes fail, and those retry silently on the next off-route fix, as on the web.
  - Spots: online only. Writes show an error and nothing is queued (no offline sync in v1).
  - Sign-in: online only.
- `ITSAppUsesNonExemptEncryption: false` (HTTPS only), as in Cockpit.

## Project layout (`ios/`)

```
ios/
  project.yml              # XcodeGen; Bankjes.xcodeproj is generated, not committed
  .gitignore               # copied from ios-cockpit (xcodeproj, build/, Info.plist, *.entitlements, .build)
  App/                     # SwiftUI: BankjesApp, MapScreen, NearMeList, NavView, SignIn, SpotsList, SpotForm
  Packages/BankjesCore/    # Foundation-only: models, API client, RouteFollower, distance/sort, Keychain wrapper
    Sources/BankjesCore/
    Sources/BankjesChecks/ # `swift run BankjesChecks ../../Fixtures`; exit 0 = pass (Cockpit pattern, no XCTest)
  Fixtures/                # items-sample.json, route-ors.json, route-osrm.json, spots.json, written by a backend test helper
  Resources/Assets.xcassets  # AppIcon derived from app/static/icon-512.png / silhouette
  bin/sim  bin/device  bin/testflight
  tools/asc_key.py
```

**Reuse from `projects/ios-cockpit` (myworkspace).** Copy, don't share; it is a different repo.

| Item | Action |
|---|---|
| `project.yml` | Copy the skeleton. Change: `name: Bankjes`; `PRODUCT_BUNDLE_IDENTIFIER: app.stephensprive.bankjes`; `DEVELOPMENT_TEAM: ${BANKJES_TEAM_ID}`; drop the widget include, Face ID/camera/mic/photos strings and the URL scheme; add the location string, `entitlements: {path: App/Bankjes.entitlements, properties: {com.apple.developer.associated-domains: ["applinks:bankjes.stephenadei.nl", "applinks:bankjes-acc.stephensprive.app"]}}`; add a per-config build setting `BANKJES_API_BASE` exposed through Info.plist (Release → prd, Debug → acc, see D1). Deployment target iOS 17. |
| `Packages/CockpitCore/Package.swift` + `CockpitChecks` `check()` harness | Copy the pattern only (about 15 lines): an executable checks target that runs on the Command Line Tools. Cockpit's checks themselves don't apply. |
| `bin/sim` | Copy and rename the scheme, project and app path. |
| `bin/device` | Copy and rename `COCKPIT_TEAM_ID` → `BANKJES_TEAM_ID`. Caveat: a free Personal Team **cannot** sign Associated Domains, so on a free-team device build the Universal Link sign-in does not work. Keep the script for the map and navigation, and test sign-in via TestFlight or the paid team. |
| `bin/testflight` + `tools/asc_key.py` | Copy and rename the scheme, archive and checks command. **Reuse the same ASC API key**: it is team-scoped, not app-scoped. It sits in Infisical (project `ios-cockpit`, env `prod`, path `/asc`, moved to the new vault in R4 per myworkspace#1233) and the Mac reads it through the existing `~/.config/asc/infisical.env` bootstrap. Nothing new goes into Infisical. |
| Signing | **Manual** for archive and export (corrected 2026-11-20: the shared ASC key is App Manager, so Xcode cloud/automatic distribution signing fails, as it did for Cockpit). The App ID `app.stephensprive.bankjes` is registered with Associated Domains; the App Store profile "Bankjes App Store" was created via the ASC API (`POST /v1/profiles`, `IOS_APP_STORE`) with the "Apple Distribution" certificate in the login keychain. `bin/testflight --preflight` checks both; Debug and `bin/device` stay automatic. |

## Slices

Backend slices go first and ship through the normal chain (feature → `develop`/acc → pre → prd release PR). iOS slices can start in parallel against acc, but S6 (auth) needs B1 on the target env.

| # | Owner | Deliverable | Acceptance check | Depends on |
|---|---|---|---|---|
| **B1** | VPS (backend) | Bearer auth + app magic link + AASA: the `app/auth.py` changes above (`client` field, `/auth/app`, `/api/auth/token`, `_consume_magic_token` extraction, bearer in `get_current_user`) and the AASA route in `app/main.py` | `python3 -m pytest` is green, including the 7 new tests. On acc: `curl -s https://bankjes-acc.stephensprive.app/.well-known/apple-app-site-association` returns JSON with `QQS3VCWWUJ.app.stephensprive.bankjes`; a live magic-link request with `client:"ios"` emails an `/auth/app` link; exchanging it and calling `/api/me` with Bearer returns 200; the existing web login still works (QA job green) | – |
| **B1b** | VPS (backend) | Promote B1 to prd (the release PR `pre → master`, merged by Stephen) | `curl https://bankjes.stephenadei.nl/.well-known/apple-app-site-association` returns 200 JSON, and Apple's CDN shows it: `curl https://app-site-association.cdn-apple.com/a/v1/bankjes.stephenadei.nl` | B1, acc/pre QA green |
| **I1** | Mac (iOS) | Skeleton + pipeline: `ios/project.yml`, an empty SwiftUI app with a map centred on Amsterdam, `BankjesCore` + `BankjesChecks`, `bin/sim`, `bin/device`, `bin/testflight`, AppIcon | `bin/sim` builds; `swift run BankjesChecks` exits 0; `bin/testflight` uploads build 1, which appears in TestFlight for Stephen (internal tester) | Stephen: ASC app record (S-1) |
| **I2** | Mac (iOS) | Map + clusters: `APIClient.items()` (decode `id, lat, lon, props.source_type`), disk cache of the last good response, MapKit `Annotation`s with `clusteringIdentifier` (UIKit `MKMapView` wrapper if SwiftUI `Map` clustering is too limited on iOS 17), a stale-data banner offline | BankjesChecks decodes `items-sample.json`. On the simulator: about 7,700 markers cluster at city zoom and split on zoom-in; airplane mode on relaunch shows the cached map plus the banner | I1 |
| **I3** | Mac (iOS) | Near me: When-In-Use permission, a list of the nearest 50 benches sorted by haversine distance, tap to centre on the map. A denied permission falls back to "Dam" as the origin with an explanation | A check sorts a fixture by distance correctly. The simulator with a custom location shows the correct nearest bench first | I2 |
| **I4** | Mac (iOS) | Navigation: `/api/route` client, preview sheet (mode picker, distance/ETA, steps), `RouteFollower` port, live state with speech, idle timer off, reroute, arrival; error texts and the Open-in-Kaarten fallback | BankjesChecks replays a GPS trace against `route-ors.json` and asserts step advances, one reroute after 3 off-route fixes, and arrival at 15 m. On the simulator, a GPX walk along the route speaks each step in Dutch; wheelchair works against acc (ORS key present) | I3 |
| **I5** | Mac (iOS) | Sign-in: email screen → `request-magic-link {client:"ios"}`, `.onOpenURL` → `/api/auth/token`, Keychain storage, Bearer on every request, 401 → sign-in screen, sign out, env-mismatch message | On a TestFlight build against acc: request a link, tap it in Mail, the app opens signed in and the profile shows the email; kill and relaunch keeps the session; sign out clears it | B1 (acc), I1 |
| **I6** | Mac (iOS) | Spots: own Spots on the map (distinct pin), "Mijn plekjes" list, add (long-press or map centre → form: label, description, category picker), edit, delete (with confirm), request public / revoke public with the status shown (`none / requested / approved / denied / revoked`) | A check verifies the request bodies for each write (Cockpit's FakeTransport pattern). Against acc, each action reflects in `/api/spots`; another user's private Spot never appears | I5 |
| **I7** | Mac (iOS) | Release builds target prd, then the friends round | Release build on TestFlight → sign in on prd → Spots CRUD works; external testers can install | B1b, I6, Stephen: S-2/S-3 |

Skipped: a compact or bbox items endpoint, because 131 KB gzipped is fine; add one if the bench count grows by roughly 10× or cold launches are noticeably slow. Also skipped: token refresh, offline write queue, push notifications. Add any of them when a tester asks.

## Open decisions for Stephen

| # | Decision | Recommendation |
|---|---|---|
| D1 | Which env TestFlight builds hit | **Release (TestFlight) → prd**; Debug (simulator/device) → acc. Friends' accounts and Spots then live where they persist, and acc gets redeployed and may be reset on every merge. Prd's coming-soon page doesn't block the API. Cost: B1 must reach prd before the friends round (I7). |
| D2 | Keep navigating with the screen locked | **Yes.** Add `UIBackgroundModes: location`, only while navigating, under When-In-Use (blue indicator), with speech continuing through an audio session. Without it, the guidance stops as soon as the phone goes into a pocket, which defeats turn-by-turn. |
| D3 | Datasets on the map in v1 | **Benches only** (`dataset=bench`) plus own and public Spots. The other five Datasets would roughly double the payload and need a filter UI; add a toggle in v2 if asked. |
| D4 | Fix the degraded-merge cache bug first (side finding) | **Yes, as a separate small backend issue before I7.** Prd currently serves 345 instead of about 7,700 benches for up to an hour after any Overpass blip, and the app would inherit that silently. The smallest fix is to not cache a merge that came back degraded (or cache it with a short TTL). |

## Steps only Stephen can do

1. **S-1. Create the App Store Connect app record**: App Store Connect → Apps → + → iOS, name "Bankjes" (or "Stephen's Bankjes"), bundle ID `app.stephensprive.bankjes` (register it first under Identifiers if it does not show in the dropdown, with Associated Domains enabled), SKU `bankjes-ios`. The ASC API cannot create app records. This is needed before I1's upload.
2. **S-2. TestFlight testers**: add himself as an internal tester. Create an external group "Vrienden", fill in the beta app description, feedback email and test notes (sign-in works by magic link to any email, so the reviewer can use their own address), and submit the first external build for Beta App Review (usually under a day). Then invite friends by email or a public link.
3. **S-3. Merge the prd release PR** carrying B1 (and D4), as for every prd change. It has the `no-automerge` label.
4. **S-4. Confirm the Associated Domains capability** on the App ID if automatic signing did not enable it (only if the I1/I5 check fails).
