// BankjesChecks: the BankjesCore checks, runnable with the Command Line Tools alone (no XCTest there).
//   swift run BankjesChecks [path/to/Fixtures]     exit 0 = all passed
// Pattern copied from ios-cockpit's CockpitChecks; the checks themselves are Bankjes' own.
import BankjesCore
import Foundation

var failures = 0, passed = 0
func check(_ ok: @autoclosure () -> Bool, _ what: String, line: Int = #line) {
    if ok() { passed += 1 } else { failures += 1; print("FAIL line \(line): \(what)") }
}

let fixtures = URL(fileURLWithPath: CommandLine.arguments.dropFirst().first
    ?? URL(fileURLWithPath: #filePath).deletingLastPathComponent().appending(path: "../../../../Fixtures").path)
var isDir: ObjCBool = false
check(FileManager.default.fileExists(atPath: fixtures.path, isDirectory: &isDir) && isDir.boolValue, "Fixtures directory at \(fixtures.path)")

// MARK: environment (D1: Debug → acc, Release → prd, via Info.plist BankjesAPIBase)
check(AppEnvironment(infoValue: "https://bankjes-acc.stephensprive.app") == .acc, "acc base parses")
check(AppEnvironment(infoValue: "https://bankjes.stephenadei.nl/") == .prd, "trailing slash dropped")
check(AppEnvironment(infoValue: "http://bankjes.stephenadei.nl") == nil, "http refused")
check(AppEnvironment(infoValue: "$(BANKJES_API_BASE)") == nil, "unexpanded build setting refused")
check(AppEnvironment(infoValue: nil) == nil && AppEnvironment(infoValue: "") == nil && AppEnvironment(infoValue: 42) == nil, "missing / empty / non-string refused")
check(AppEnvironment.acc.label == "acc" && AppEnvironment.prd.label == "prd", "env labels")
check(abs(Coordinate.dam.lat - 52.3731) < 1e-9 && abs(Coordinate.dam.lon - 4.8926) < 1e-9, "Dam coordinate")

// MARK: items contract (I2): a real acc response sample, GET /api/items?dataset=bench on 2026-11-20
let sampleData = try! Data(contentsOf: fixtures.appending(path: "items-sample.json"))
let sample = try! ItemsResponse.decode(sampleData)
check(sample.count == 179 && sample.items.count == 179, "179 sample benches decode")
check(sample.items.filter { $0.source == .bgt }.count == 30 && sample.items.filter { $0.source == .osm }.count == 149, "30 BGT + 149 OSM")
check(sample.items.filter { $0.backrest == true }.count == 74 && sample.items.filter { $0.backrest == false }.count == 67, "backrest yes 74 / no 67")
check(sample.items.filter { $0.source == .bgt }.allSatisfy { $0.backrest == nil }, "BGT benches: backrest unknown")
let b0 = sample.items.first { $0.id == "osm:5413184786" }
check(b0 != nil && abs(b0!.coordinate.lat - 52.3729) < 0.001 && b0!.backrest == false, "known OSM bench near the Dam")
check(Set(sample.items.map(\.id)).count == sample.items.count, "ids unique")
let messy = try! ItemsResponse.decode(Data(#"{"count":5,"items":[{"id":"a","lat":52.1,"lon":4.9,"props":{"source_type":"osm","backrest":"YES"}},{"id":"b","lat":"x","lon":4.9},{"id":"c","lat":91,"lon":4.9,"props":{}},{"id":"","lat":52,"lon":4},{"id":"e","lat":52.2,"lon":4.8,"props":{"source_type":7,"backrest":1}},{"id":"f","lat":52.2,"lon":4.8}]}"#.utf8))
check(messy.items.map(\.id) == ["a", "e", "f"], "bad rows dropped, the rest stays")
check(messy.items[0].backrest == true && messy.items[0].source == .osm, "backrest case-insensitive")
check(messy.items[1].source == .other && messy.items[1].backrest == nil && messy.items[2].source == .other, "odd/missing props → unknown")
check(messy.count == 5, "count is the server's")
check((try? ItemsResponse.decode(Data("[]".utf8))) == nil, "a non-object body is an error")

// A recording fake transport.
final class FakeTransport: HTTPTransport, @unchecked Sendable {
    var requests: [URLRequest] = []
    var reply: (Int, Data) = (200, Data())
    var fail: Error?
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        requests.append(request)
        if let fail { throw fail }
        return (reply.1, HTTPURLResponse(url: request.url!, statusCode: reply.0, httpVersion: nil, headerFields: nil)!)
    }
}
func run<T>(_ body: @escaping @Sendable () async -> T) -> T {
    let box = UnsafeMutablePointer<T?>.allocate(capacity: 1); box.initialize(to: nil)
    let sem = DispatchSemaphore(value: 0)
    Task { box.pointee = await body(); sem.signal() }
    sem.wait()
    defer { box.deallocate() }
    return box.pointee!
}

let fake = FakeTransport()
let client = APIClient(environment: .acc, transport: fake)
check(client.itemsRequest().url?.absoluteString == "https://bankjes-acc.stephensprive.app/api/items?dataset=bench", "items URL on acc")
check(APIClient(environment: .prd, transport: fake).itemsRequest().url?.absoluteString == "https://bankjes.stephenadei.nl/api/items?dataset=bench", "items URL on prd")
check(client.itemsRequest().httpMethod == "GET" && client.itemsRequest().value(forHTTPHeaderField: "Accept") == "application/json", "GET, Accept json")
fake.reply = (200, sampleData)
let got = run { try? await client.items() }
check(got?.benches.count == 179 && got?.raw == sampleData, "items() decodes and returns the raw body")
fake.reply = (502, Data(#"{"detail":"Upstream unavailable for dataset: bench"}"#.utf8))
let e502 = run { () -> APIError? in do { _ = try await client.items(); return nil } catch { return error as? APIError } }
check(e502 == .http(status: 502, detail: "Upstream unavailable for dataset: bench"), "502 carries the server's detail")
fake.reply = (200, Data("<html>".utf8))
let eDec = run { () -> APIError? in do { _ = try await client.items(); return nil } catch { return error as? APIError } }
if case .decoding = eDec { check(true, "") } else { check(false, "garbage body → decoding error") }
fake.fail = URLError(.notConnectedToInternet)
let eNet = run { () -> APIError? in do { _ = try await client.items(); return nil } catch { return error as? APIError } }
if case .transport = eNet { check(true, "") } else { check(false, "offline → transport error") }
fake.fail = nil

// MARK: disk cache + repository (offline banner)
let tmp = FileManager.default.temporaryDirectory.appending(path: "bankjes-checks-\(UUID().uuidString)")
let cache = ItemsCache(directory: tmp)
let repo = BenchRepository(client: client, cache: cache)
check(cache.load() == nil && repo.cachedOnly() == nil, "no cache yet")
fake.fail = URLError(.notConnectedToInternet)
if case .unavailable = run({ await repo.load() }) { check(true, "") } else { check(false, "first launch offline → unavailable") }
fake.fail = nil; fake.reply = (200, sampleData)
let t0 = Date(timeIntervalSince1970: 1_790_000_000)
if case .fresh(let b, let at) = run({ await repo.load(now: t0) }) { check(b.count == 179 && at == t0, "online → fresh") } else { check(false, "online → fresh") }
check(cache.load()?.benches.count == 179 && cache.load()?.fetchedAt == t0, "fresh response written to the cache with its time")
fake.fail = URLError(.timedOut)
if case .cached(let b, let at, _) = run({ await repo.load() }) { check(b.count == 179 && at == t0, "offline → cached, with the old time") } else { check(false, "offline → cached") }
check(repo.cachedOnly()?.benches.count == 179, "cachedOnly for the first frame")
fake.fail = nil; fake.reply = (200, Data(#"{"count":0,"items":[]}"#.utf8))
if case .cached(let b, _, _) = run({ await repo.load() }) { check(b.count == 179, "an empty response does not replace a good cache") } else { check(false, "empty response keeps cache") }
fake.reply = (502, Data())
if case .cached = run({ await repo.load() }) { check(true, "") } else { check(false, "502 → cached") }
try! Data("corrupt".utf8).write(to: cache.file)
check(cache.load() == nil, "a corrupt cache is ignored")

// MARK: near me (I3): haversine + nearest 50
let centraal = Coordinate(lat: 52.3791, lon: 4.9003)
check(abs(Geo.distance(.dam, centraal) - 847.54) < 0.5, "Dam → Centraal ≈ 847.5 m (independent Python haversine)")
check(Geo.distance(.dam, .dam) == 0, "zero distance")
check(abs(Geo.distance(Coordinate(lat: 0, lon: 0), Coordinate(lat: 0, lon: 1)) - 111_195.08) < 1, "one degree on the equator")
check(abs(Geo.distance(.dam, centraal) - Geo.distance(centraal, .dam)) < 1e-9, "symmetric")
let near = Geo.nearest(sample.items, to: .dam)
check(near.count == 50, "nearest 50")
check(near.prefix(5).map(\.bench.id) == ["osm:5413184786", "osm:5413184787", "osm:5413184785", "osm:5413184784", "osm:5413184791"], "nearest five to the Dam, as computed in Python on the full acc set")
check(abs(near[0].metres - 23.7) < 0.1, "nearest bench 23.7 m from the Dam")
check(zip(near, near.dropFirst()).allSatisfy { $0.metres <= $1.metres }, "sorted nearest first")
let brute = sample.items.map { Geo.distance(.dam, $0.coordinate) }.sorted()
check(near.map(\.metres) == Array(brute.prefix(50)), "same distances as a brute-force sort")
let far = Coordinate(lat: 52.40, lon: 4.80)
check(Geo.nearest(sample.items, to: far, limit: 3).map(\.bench.id) == sample.items.sorted { Geo.distance(far, $0.coordinate) < Geo.distance(far, $1.coordinate) }.prefix(3).map(\.id), "another origin")
check(Geo.nearest(sample.items, to: .dam, limit: 0).isEmpty && Geo.nearest([], to: .dam).isEmpty, "limit 0 / no benches")
let twins = [Bench(id: "b", coordinate: .dam, source: .osm, backrest: nil), Bench(id: "a", coordinate: .dam, source: .osm, backrest: nil)]
check(Geo.nearest(twins, to: .dam).map(\.bench.id) == ["a", "b"], "ties broken by id")
let nl = Locale(identifier: "nl_NL"), en = Locale(identifier: "en_GB")
check(Geo.formatDistance(23.7, locale: nl) == "20 m" && Geo.formatDistance(3, locale: nl) == "10 m", "metres round to 10")
check(Geo.formatDistance(996, locale: nl) == "1,0 km", "996 m → 1,0 km")
check(Geo.formatDistance(1234, locale: nl) == "1,2 km" && Geo.formatDistance(1234, locale: en) == "1.2 km", "km with the locale's decimal")
check(Geo.formatDistance(12_400, locale: nl) == "12 km", "no decimal from 10 km")

// MARK: sign-in (I5): magic link client "ios", token exchange, Bearer, 401, env mismatch, link parser
func body(_ r: URLRequest) -> [String: String]? {
    r.httpBody.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: String] }
}
let authFake = FakeTransport()
let store = MemorySessionStore()
let sessions = SessionManager(store: store)
final class ChangeLog: @unchecked Sendable { var all: [SessionManager.Change] = [] }
let log = ChangeLog()
sessions.onChange = { log.all.append($0) }
let authClient = APIClient(environment: .acc, transport: authFake, session: sessions)
check(!sessions.isSignedIn && sessions.user == nil, "starts signed out")

// request-magic-link body
let mlReq = authClient.magicLinkRequest(email: "ann@example.nl")
check(mlReq.url?.absoluteString == "https://bankjes-acc.stephensprive.app/api/auth/request-magic-link", "magic-link URL on acc")
check(mlReq.httpMethod == "POST" && mlReq.value(forHTTPHeaderField: "Content-Type") == "application/json", "magic-link: POST json")
check(body(mlReq) == ["email": "ann@example.nl", "client": "ios"], "magic-link body {email, client:\"ios\"}")
authFake.reply = (200, Data(#"{"sent":true}"#.utf8))
let mlOK = run { () -> Bool in (try? await authClient.requestMagicLink(email: "ann@example.nl")) != nil }
check(mlOK && authFake.requests.last.flatMap(body) == ["email": "ann@example.nl", "client": "ios"], "requestMagicLink sends that body")
check(authFake.requests.last?.value(forHTTPHeaderField: "Authorization") == nil, "no Authorization while signed out")
authFake.reply = (400, Data(#"{"detail":"invalid email"}"#.utf8))
let mlBad = run { () -> APIError? in do { try await authClient.requestMagicLink(email: "x"); return nil } catch { return error as? APIError } }
check(mlBad == .http(status: 400, detail: "invalid email"), "400 invalid email surfaces")
check(EmailAddress.normalise("  Ann@Example.NL ") == "ann@example.nl", "email trimmed + lowercased")
check(["", "ann", "ann@", "@example.nl", "ann@example", "ann@example.", "a b@example.nl", "a@b@c.nl", "ann@.nl"].allSatisfy { EmailAddress.normalise($0) == nil }, "bad emails refused (backend's rule)")

// token exchange
let teReq = authClient.tokenExchangeRequest(token: "MAGIC.tok-1")
check(teReq.url?.absoluteString == "https://bankjes-acc.stephensprive.app/api/auth/token" && teReq.httpMethod == "POST", "token URL, POST")
check(body(teReq) == ["token": "MAGIC.tok-1"], "token body {token}")
let userJSON = #"{"id":"u-1","email":"ann@example.nl","display_name":"ann","is_admin":false}"#
authFake.reply = (200, Data(#"{"session":"SESS-abc","user":\#(userJSON)}"#.utf8))
let signedUser = run { try? await authClient.signIn(withMagicToken: "MAGIC.tok-1") }
check(signedUser == AuthUser(id: "u-1", email: "ann@example.nl", displayName: "ann", isAdmin: false), "exchange decodes the user")
check(store.load()?.session == "SESS-abc" && store.load()?.user.email == "ann@example.nl", "session + user stored")
check(sessions.isSignedIn && log.all.last == .signedIn(signedUser!), "signed-in change")
check(SessionManager(store: store).user?.email == "ann@example.nl", "relaunch: the stored session is picked up")
authFake.reply = (400, Data(#"{"detail":"invalid token"}"#.utf8))
let badTok = run { () -> APIError? in do { try await APIClient(environment: .acc, transport: authFake, session: SessionManager(store: MemorySessionStore())).signIn(withMagicToken: "TEST"); return nil } catch { return error as? APIError } }
check(badTok == .http(status: 400, detail: "invalid token"), "bad magic token → 400 invalid token, nothing stored")
authFake.reply = (200, Data(#"{"session":"S"}"#.utf8))
let badShape = run { () -> APIError? in do { _ = try await authClient.exchangeToken("t"); return nil } catch { return error as? APIError } }
check(badShape == .decoding("token exchange response"), "malformed exchange body → decoding error without the body")

// Bearer on every request
authFake.reply = (200, sampleData)
_ = run { try? await authClient.items() }
check(authFake.requests.last?.value(forHTTPHeaderField: "Authorization") == "Bearer SESS-abc", "Bearer on items")
authFake.reply = (200, Data(#"{"id":"u-1","email":"ann@example.nl","display_name":"Ann B","is_admin":false}"#.utf8))
let meUser = run { try? await authClient.me() }
check(authFake.requests.last?.url?.path == "/api/me" && authFake.requests.last?.value(forHTTPHeaderField: "Authorization") == "Bearer SESS-abc", "Bearer on /api/me")
check(meUser?.displayName == "Ann B" && store.load()?.user.displayName == "Ann B" && store.load()?.session == "SESS-abc", "/api/me refreshes the stored user")
authFake.reply = (200, Data(#"{"sent":true}"#.utf8))
_ = run { try? await authClient.requestMagicLink(email: "ann@example.nl") }
check(authFake.requests.last?.value(forHTTPHeaderField: "Authorization") == "Bearer SESS-abc", "Bearer on POSTs too")
check(authClient.itemsRequest().value(forHTTPHeaderField: "Authorization") == nil, "the Bearer is added at send time, not baked into requests")

// 401 → signed out
// A sign-in that lands while an old request is in flight: that request's 401 must not sign out the new session.
final class RacingTransport: HTTPTransport, @unchecked Sendable {
    let during: () -> Void
    init(during: @escaping () -> Void) { self.during = during }
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        during()
        return (Data(), HTTPURLResponse(url: request.url!, statusCode: 401, httpVersion: nil, headerFields: nil)!)
    }
}
let raced = SessionManager(store: MemorySessionStore(StoredSession(session: "OLD", user: signedUser!)))
let racer = APIClient(environment: .acc, transport: RacingTransport { try? raced.signIn(StoredSession(session: "NEW", user: signedUser!)) }, session: raced)
_ = run { try? await racer.me() }
check(raced.isSignedIn, "a 401 for an older Bearer does not sign out the newer session")
authFake.reply = (401, Data(#"{"detail":"not authenticated"}"#.utf8))
let e401 = run { () -> APIError? in do { _ = try await authClient.me(); return nil } catch { return error as? APIError } }
check(e401?.isUnauthorized == true, "401 surfaces as unauthorized")
check(!sessions.isSignedIn && store.load() == nil && log.all.last == .expired, "401 → signed out, Keychain cleared, expired change")
_ = run { try? await authClient.items() }
check(authFake.requests.last?.value(forHTTPHeaderField: "Authorization") == nil, "no Bearer after the 401")
authFake.reply = (401, Data())
let anon401 = run { () -> APIError? in do { _ = try await authClient.me(); return nil } catch { return error as? APIError } }
check(anon401?.isUnauthorized == true && log.all.last == .expired && log.all.filter { $0 == .expired }.count == 1, "a 401 while signed out does not fire again")
try! sessions.signIn(StoredSession(session: "S2", user: signedUser!))
sessions.signOut()
check(!sessions.isSignedIn && store.load() == nil && log.all.last == .signedOut, "sign out clears the store")

// the link parser + env mismatch
let accTok = URL(string: "https://bankjes-acc.stephensprive.app/auth/app?token=abc.DEF-123")!
let prdTok = URL(string: "https://bankjes.stephenadei.nl/auth/app?token=abc")!
check(MagicLink.parse(accTok, for: .acc) == .token("abc.DEF-123"), "acc link in an acc build → token")
check(MagicLink.parse(prdTok, for: .prd) == .token("abc"), "prd link in a prd build → token")
check(MagicLink.parse(prdTok, for: .acc) == .wrongEnvironment(link: .prd, app: .acc), "prd link in an acc (Debug) build → mismatch")
check(MagicLink.parse(accTok, for: .prd) == .wrongEnvironment(link: .acc, app: .prd), "acc link in a prd build → mismatch")
check(MagicLink.parse(URL(string: "https://BANKJES-ACC.stephensprive.app/auth/app?token=t")!, for: .acc) == .token("t"), "host case-insensitive")
let custom = AppEnvironment(apiBase: URL(string: "https://bankjes-test.example.org")!)
check(MagicLink.parse(accTok, for: custom) == .wrongEnvironment(link: .acc, app: custom), "a Debug override host: acc links are a mismatch")
let rejects = [
    "https://evil.example/auth/app?token=t",                         // foreign host
    "https://bankjes-acc.stephensprive.app.evil.example/auth/app?token=t",
    "https://evil.example/bankjes-acc.stephensprive.app/auth/app?token=t",
    "https://bankjes-acc.stephensprive.app/auth/verify?token=t",      // the web login path
    "https://bankjes-acc.stephensprive.app/auth/application?token=t",
    "https://bankjes-acc.stephensprive.app/x/auth/app?token=t",
    "https://bankjes-acc.stephensprive.app/?token=t",
    "http://bankjes-acc.stephensprive.app/auth/app?token=t",          // not https
    "bankjes://auth/app?token=t",
    "https://bankjes-acc.stephensprive.app:8443/auth/app?token=t",    // another port
    "https://u:p@bankjes-acc.stephensprive.app/auth/app?token=t",
    "https://bankjes-acc.stephensprive.app/auth/app",                 // no token
    "https://bankjes-acc.stephensprive.app/auth/app?token=",
    "https://bankjes-acc.stephensprive.app/auth/app?token=a&token=b", // ambiguous
]
let wrongly = rejects.filter { MagicLink.parse(URL(string: $0)!, for: .acc) != .rejected }
check(wrongly.isEmpty, "foreign host / path / scheme / port / token-less links rejected: \(wrongly)")
check(MagicLink.parse(URL(string: "https://evil.example/auth/app?token=t")!, for: .prd) == .rejected, "foreign host rejected in prd too")

// token hygiene: nothing that holds a token or session prints it
let stored = StoredSession(session: "SESS-SECRET", user: signedUser!)
let printed = [String(describing: stored), String(reflecting: stored), "\(MagicLink.token("MAGIC-SECRET"))", String(describing: sessions)].joined()
check(!printed.contains("SESS-SECRET") && !printed.contains("MAGIC-SECRET"), "descriptions redact the session and the magic token")

// MARK: Spots (I6): decoding, the device-side ACL, validation, and every write's method/path/body
let spotsData = try! Data(contentsOf: fixtures.appending(path: "spots.json"))
let allSpots = try! SpotsResponse.decode(spotsData).spots
check(allSpots.count == 9, "9 fixture Spots decode")
let s1 = allSpots.first { $0.id.hasSuffix("0001") }!
check(s1.label == "Bankje achter het Paleis" && s1.category == .bank && s1.visibility == .private && s1.publicStatus == .none
      && s1.owner == Spot.Owner(id: "u-1", displayName: "ann") && abs(s1.coordinate.lat - 52.37445) < 1e-9 && s1.createdAt == "2026-11-18 09:12:00", "Spot fields")
check(Set(allSpots.map(\.publicStatus)) == [.none, .requested, .approved, .denied, .revoked], "all five public_status values decode")
check(allSpots.first { $0.id.hasSuffix("0002") }?.description == nil && allSpots.first { $0.id.hasSuffix("0007") }?.owner.displayName == nil, "null description / display_name → nil")
check(allSpots.first { $0.id.hasSuffix("0003") }.map { $0.visibility == .public && $0.publicStatus == .approved && $0.isPublicApproved } == true, "approved public")
let oddSpots = try! SpotsResponse.decode(Data(#"{"spots":[{"id":"a","lat":52,"lon":4,"label":"x","category":"troon","visibility":"friends","public_status":"pending","owner":{"id":"u-1"}},{"id":"b","lat":95,"lon":4,"label":"x","owner":{"id":"u"}},{"id":"c","lat":52,"lon":4,"label":"x"}]}"#.utf8)).spots
check(oddSpots.map(\.id) == ["a"] && oddSpots[0].category == nil && oddSpots[0].visibility == .friends && oddSpots[0].publicStatus == .unknown, "unknown values tolerated, bad rows dropped")

// The ACL: another user's private (or still pending) Spot never appears.
let visibleToAnn = SpotFilter.visible(allSpots, to: "u-1")
check(visibleToAnn.count == 7, "ann sees her 5 + 2 approved public")
check(!visibleToAnn.contains { $0.id.hasSuffix("0008") || $0.id.hasSuffix("0009") }, "bob's private and pending Spots never reach ann")
check(SpotFilter.own(allSpots, userId: "u-1").count == 5 && SpotFilter.own(allSpots, userId: nil).isEmpty, "own Spots by owner id; none signed out")
let anon = SpotFilter.visible(allSpots, to: nil)
check(anon.map(\.id).sorted() == allSpots.filter { $0.id.hasSuffix("0003") || $0.id.hasSuffix("0006") || $0.id.hasSuffix("0007") }.map(\.id).sorted(), "signed out: only public + approved")
check(SpotFilter.visible(allSpots, to: "u-2").contains { $0.id.hasSuffix("0008") } && !SpotFilter.visible(allSpots, to: "u-2").contains { $0.id.hasSuffix("0001") }, "bob sees his own private one, not ann's")

// status → which action is offered
let byStatus = Dictionary(allSpots.filter { $0.owner.id == "u-1" }.map { ($0.publicStatus, $0) }, uniquingKeysWith: { a, _ in a })
check(byStatus[.none]!.canRequestPublic && !byStatus[.none]!.canRevokePublic, "none → request")
check(!byStatus[.requested]!.canRequestPublic && byStatus[.requested]!.canRevokePublic, "requested → revoke")
check(!byStatus[.approved]!.canRequestPublic && byStatus[.approved]!.canRevokePublic, "approved → revoke (request would 409)")
check(byStatus[.denied]!.canRequestPublic && byStatus[.revoked]!.canRequestPublic && !byStatus[.revoked]!.canRevokePublic, "denied / revoked → request again")

// validation (the backend's pydantic rules)
check(SpotDraft(label: "  ").problems == [.labelEmpty], "blank label refused")
check(SpotDraft(label: String(repeating: "a", count: 60)).isValid && SpotDraft(label: String(repeating: "a", count: 61)).problems == [.labelTooLong], "label ≤ 60")
check(SpotDraft(label: "x", description: String(repeating: "d", count: 401)).problems == [.descriptionTooLong] && SpotDraft(label: "x", description: String(repeating: "d", count: 400)).isValid, "description ≤ 400")
check(SpotCategory.allCases.map(\.rawValue) == ["bank", "stoel", "picknicktafel", "krukje", "anders"], "categories = backend CATEGORIES")

func jsonBody(_ r: URLRequest?) -> NSDictionary? {
    r?.httpBody.flatMap { try? JSONSerialization.jsonObject(with: $0) as? NSDictionary }
}
func spotJSON(id: String = "new-1", label: String = "Nieuw", status: String = "none", visibility: String = "private") -> Data {
    Data(#"{"id":"\#(id)","lat":52.37,"lon":4.89,"label":"\#(label)","description":null,"category":"bank","visibility":"\#(visibility)","public_status":"\#(status)","created_at":"2026-11-20 12:00:00","owner":{"id":"u-1","display_name":"ann"}}"#.utf8)
}
let spotFake = FakeTransport()
let annSession = SessionManager(store: MemorySessionStore(StoredSession(session: "SESS-ann", user: AuthUser(id: "u-1", email: "ann@example.nl", displayName: "ann", isAdmin: false))))
let spotClient = APIClient(environment: .acc, transport: spotFake, session: annSession)
let base = "https://bankjes-acc.stephensprive.app"
func lastIs(_ method: String, _ path: String) -> Bool {
    spotFake.requests.last.map { $0.httpMethod == method && $0.url?.absoluteString == base + path } ?? false
}

// GET /api/spots: Bearer, filtered
spotFake.reply = (200, spotsData)
let listed = run { try? await spotClient.spots() }
check(lastIs("GET", "/api/spots") && spotFake.requests.last?.httpBody == nil, "GET /api/spots")
check(spotFake.requests.last?.value(forHTTPHeaderField: "Authorization") == "Bearer SESS-ann", "Bearer on /api/spots")
check(listed?.count == 7 && listed?.contains { $0.owner.id == "u-2" && !$0.isPublicApproved } == false, "spots(): another user's private Spot filtered out")
let anonClient = APIClient(environment: .acc, transport: spotFake, session: SessionManager(store: MemorySessionStore()))
check(run { try? await anonClient.spots() }?.count == 3 && spotFake.requests.last?.value(forHTTPHeaderField: "Authorization") == nil, "signed out: no Bearer, public only")

// POST /api/spots
let draft = SpotDraft(label: "  Bankje bij de gracht ", description: " Mooi uitzicht ", category: .picknicktafel)
let at = Coordinate(lat: 52.3712, lon: 4.8899)
spotFake.reply = (200, spotJSON(label: "Bankje bij de gracht"))
let created = run { try? await spotClient.createSpot(draft, at: at) }
check(lastIs("POST", "/api/spots"), "create: POST /api/spots")
check(spotFake.requests.last?.value(forHTTPHeaderField: "Content-Type") == "application/json", "create: JSON")
check(jsonBody(spotFake.requests.last) == ["lat": 52.3712, "lon": 4.8899, "label": "Bankje bij de gracht", "description": "Mooi uitzicht", "category": "picknicktafel"], "create body {lat, lon, label, description, category}, trimmed")
check(created?.id == "new-1" && created?.publicStatus == SpotPublicStatus.none, "create returns the Spot")
check(jsonBody(spotClient.createSpotRequest(SpotDraft(label: "x", description: "  ", category: .anders), at: at)) == ["lat": 52.3712, "lon": 4.8899, "label": "x", "category": "anders"], "empty description left out")

// PATCH /api/spots/{id}: only what changed
var edit = SpotDraft(s1)
edit.label = "Bankje achter het Paleis (oost)"
spotFake.reply = (200, spotJSON(id: s1.id, label: edit.label))
let patched = run { try? await spotClient.updateSpot(s1, with: edit) }
check(lastIs("PATCH", "/api/spots/\(s1.id)") && jsonBody(spotFake.requests.last) == ["label": "Bankje achter het Paleis (oost)"], "edit: PATCH with only the label")
check(patched?.label == "Bankje achter het Paleis (oost)", "edit returns the updated Spot")
edit = SpotDraft(s1); edit.description = ""; edit.category = .stoel
check(jsonBody(spotClient.updateSpotRequest(s1, with: edit)) == ["description": "", "category": "stoel"], "cleared description sent as \"\", category changed")
let before = spotFake.requests.count
let same = run { try? await spotClient.updateSpot(s1, with: SpotDraft(s1)) }
check(same == s1 && spotFake.requests.count == before, "nothing changed → no request")

// DELETE /api/spots/{id}
spotFake.reply = (200, Data(#"{"ok":true}"#.utf8))
let deleted = run { () -> Bool in (try? await spotClient.deleteSpot(id: s1.id)) != nil }
check(deleted && lastIs("DELETE", "/api/spots/\(s1.id)") && spotFake.requests.last?.httpBody == nil, "delete: DELETE /api/spots/{id}, no body")

// request-public / revoke-public
spotFake.reply = (200, spotJSON(id: s1.id, status: "requested", visibility: "public"))
let req = run { try? await spotClient.requestPublic(id: s1.id) }
check(lastIs("POST", "/api/spots/\(s1.id)/request-public") && spotFake.requests.last?.httpBody == nil, "request-public: POST, no body")
check(req?.publicStatus == .requested && req?.visibility == .public && req?.canRevokePublic == true, "request-public → requested")
spotFake.reply = (200, spotJSON(id: s1.id, status: "revoked", visibility: "private"))
let rev = run { try? await spotClient.revokePublic(id: s1.id) }
check(lastIs("POST", "/api/spots/\(s1.id)/revoke-public") && spotFake.requests.last?.httpBody == nil, "revoke-public: POST, no body")
check(rev?.publicStatus == .revoked && rev?.visibility == .private && rev?.canRequestPublic == true, "revoke-public → revoked")
check(spotFake.requests.allSatisfy { $0.value(forHTTPHeaderField: "Authorization") == "Bearer SESS-ann" || $0.value(forHTTPHeaderField: "Authorization") == nil }, "only ann's Bearer is ever sent")

// errors: 409, 403, offline (one request, nothing queued or retried)
spotFake.reply = (409, Data(#"{"detail":"already approved"}"#.utf8))
let e409 = run { () -> APIError? in do { _ = try await spotClient.requestPublic(id: "x"); return nil } catch { return error as? APIError } }
check(e409 == .http(status: 409, detail: "already approved"), "409 already approved surfaces")
spotFake.reply = (403, Data(#"{"detail":"not your spot"}"#.utf8))
let e403 = run { () -> APIError? in do { _ = try await spotClient.updateSpot(s1, with: SpotDraft(label: "y")); return nil } catch { return error as? APIError } }
check(e403 == .http(status: 403, detail: "not your spot"), "403 not your spot surfaces")
spotFake.fail = URLError(.notConnectedToInternet)
let n0 = spotFake.requests.count
let eOff = run { () -> APIError? in do { _ = try await spotClient.createSpot(draft, at: at); return nil } catch { return error as? APIError } }
if case .transport = eOff { check(spotFake.requests.count == n0 + 1, "offline create: one attempt, nothing queued") } else { check(false, "offline create → transport error") }
spotFake.fail = nil
spotFake.reply = (200, Data("{}".utf8))
let eDel = run { () -> APIError? in do { try await spotClient.deleteSpot(id: "x"); return nil } catch { return error as? APIError } }
check(eDel == .decoding("delete"), "delete without {ok:true} is not a success")
spotFake.reply = (401, Data())
_ = run { try? await spotClient.createSpot(draft, at: at) }
check(!annSession.isSignedIn, "a 401 on a Spot write signs out")

try? FileManager.default.removeItem(at: tmp)   // not a defer: exit() below skips top-level defers
print("BankjesChecks: \(passed) passed, \(failures) failed")
exit(failures == 0 ? 0 : 1)
