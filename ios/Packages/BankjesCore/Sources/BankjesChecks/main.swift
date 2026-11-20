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

try? FileManager.default.removeItem(at: tmp)   // not a defer: exit() below skips top-level defers
print("BankjesChecks: \(passed) passed, \(failures) failed")
exit(failures == 0 ? 0 : 1)
