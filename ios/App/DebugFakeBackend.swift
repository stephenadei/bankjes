#if DEBUG
import BankjesCore
import Foundation

/// Debug only (`-BankjesFakeSession 1`): a signed-in fake user ("ann", id u-1) and an in-memory Spots
/// backend seeded with the Spots of `Fixtures/spots.json`, so the I6 screens can be exercised and screenshot
/// in the simulator without a magic-link mail. Spot writes never leave the process: only `GET /api/items`
/// (read-only, no Authorization header) goes to the real backend for the benches; everything else is answered
/// here or with a 404. Never compiled into Release.
///
/// Extra screenshot hooks: `-BankjesSpots list | add | detail:<id> | request:<id>` opens that sheet after launch;
/// `-BankjesFakeOffline 1` makes every Spot write fail as if offline.
enum DebugFakeBackend {
    static let user = AuthUser(id: "u-1", email: "ann@voorbeeld.nl", displayName: "ann", isAdmin: false)

    static func fromLaunchArguments(environment: AppEnvironment) -> (session: SessionManager, client: APIClient)? {
        let d = UserDefaults.standard
        guard d.bool(forKey: "BankjesFakeSession") else { return nil }
        let session = SessionManager(store: MemorySessionStore(StoredSession(session: "debug-fake-session", user: user)))
        let transport = FakeSpotsTransport(offline: d.bool(forKey: "BankjesFakeOffline"))
        return (session, APIClient(environment: environment, transport: transport, session: session))
    }

    /// The `Fixtures/spots.json` content (the app bundle does not ship the Fixtures folder).
    static let fixtureSpots = #"""
{"spots": [
  {"id": "5b0c6a1e-0001-4c1e-9a00-000000000001", "lat": 52.37445, "lon": 4.89012, "label": "Bankje achter het Paleis", "description": "Rustig, in de middagzon.", "category": "bank", "visibility": "private", "public_status": "none", "created_at": "2026-11-18 09:12:00", "owner": {"id": "u-1", "display_name": "ann"}},
  {"id": "5b0c6a1e-0002-4c1e-9a00-000000000002", "lat": 52.37105, "lon": 4.89640, "label": "Krukje bij de Nieuwmarkt-kant", "description": null, "category": "krukje", "visibility": "public", "public_status": "requested", "created_at": "2026-11-18 10:40:00", "owner": {"id": "u-1", "display_name": "ann"}},
  {"id": "5b0c6a1e-0003-4c1e-9a00-000000000003", "lat": 52.37660, "lon": 4.88720, "label": "Picknicktafel Torensluis", "description": "Grote tafel, plek voor vier.", "category": "picknicktafel", "visibility": "public", "public_status": "approved", "created_at": "2026-11-17 14:05:00", "owner": {"id": "u-1", "display_name": "ann"}},
  {"id": "5b0c6a1e-0004-4c1e-9a00-000000000004", "lat": 52.36950, "lon": 4.88830, "label": "Stoel op het Spui", "description": "", "category": "stoel", "visibility": "private", "public_status": "denied", "created_at": "2026-11-16 08:00:00", "owner": {"id": "u-1", "display_name": "ann"}},
  {"id": "5b0c6a1e-0005-4c1e-9a00-000000000005", "lat": 52.37790, "lon": 4.89580, "label": "Muurtje aan het water", "description": "Geen echte bank, wel goed zitten.", "category": "anders", "visibility": "private", "public_status": "revoked", "created_at": "2026-11-15 17:30:00", "owner": {"id": "u-1", "display_name": "ann"}},
  {"id": "5b0c6a1e-0006-4c1e-9a00-000000000006", "lat": 52.37250, "lon": 4.90060, "label": "Bank op de Oudezijds", "description": "Openbaar plekje van een ander.", "category": "bank", "visibility": "public", "public_status": "approved", "created_at": "2026-11-14 12:00:00", "owner": {"id": "u-2", "display_name": "bob"}},
  {"id": "5b0c6a1e-0007-4c1e-9a00-000000000007", "lat": 52.36720, "lon": 4.89350, "label": "Bankjes Rokin", "description": null, "category": "bank", "visibility": "public", "public_status": "approved", "created_at": "2026-11-13 12:00:00", "owner": {"id": "u-3", "display_name": null}},
  {"id": "5b0c6a1e-0008-4c1e-9a00-000000000008", "lat": 52.37500, "lon": 4.89900, "label": "Bob's geheime plek", "description": "Privé: mag nooit bij een ander verschijnen.", "category": "bank", "visibility": "private", "public_status": "none", "created_at": "2026-11-12 12:00:00", "owner": {"id": "u-2", "display_name": "bob"}},
  {"id": "5b0c6a1e-0009-4c1e-9a00-000000000009", "lat": 52.37000, "lon": 4.89100, "label": "Bob's aanvraag", "description": "Aangevraagd, nog niet goedgekeurd: alleen voor bob.", "category": "stoel", "visibility": "public", "public_status": "requested", "created_at": "2026-11-11 12:00:00", "owner": {"id": "u-2", "display_name": "bob"}}
]}
"""#
}

final class FakeSpotsTransport: HTTPTransport, @unchecked Sendable {
    private let lock = NSLock()
    private var spots: [[String: Any]]
    private let offline: Bool
    private let network = URLSessionTransport.makeDefault()

    init(offline: Bool) {
        self.offline = offline
        let root = try? JSONSerialization.jsonObject(with: Data(DebugFakeBackend.fixtureSpots.utf8)) as? [String: Any]
        spots = root?["spots"] as? [[String: Any]] ?? []
    }

    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let url = request.url!
        let method = request.httpMethod ?? "GET"
        let parts = url.path.split(separator: "/").map(String.init)   // ["api", "spots", id, action]

        if method == "GET", parts == ["api", "items"] {
            var r = request
            r.setValue(nil, forHTTPHeaderField: "Authorization")
            return try await network.send(r)
        }
        if method == "GET", parts == ["api", "me"] {
            return reply(url, 200, ["id": DebugFakeBackend.user.id, "email": DebugFakeBackend.user.email,
                                    "display_name": DebugFakeBackend.user.displayName, "is_admin": false])
        }
        guard parts.count >= 2, parts[0] == "api", parts[1] == "spots" else { return reply(url, 404, ["detail": "not in the fake"]) }
        if method != "GET" && offline { throw URLError(.notConnectedToInternet) }
        try await Task.sleep(for: .milliseconds(250))

        let body = request.httpBody.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
        return lock.withLock { () -> (Data, HTTPURLResponse) in
            switch (method, parts.count) {
            case ("GET", 2):
                // The server's ACL: public + approved, plus own.
                let visible = spots.filter {
                    ($0["visibility"] as? String == "public" && $0["public_status"] as? String == "approved")
                        || ($0["owner"] as? [String: Any])?["id"] as? String == DebugFakeBackend.user.id
                }
                return reply(url, 200, ["spots": visible])
            case ("POST", 2):
                let now = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: "T", with: " ").replacingOccurrences(of: "Z", with: "")
                let new: [String: Any] = [
                    "id": UUID().uuidString.lowercased(), "lat": body["lat"] ?? 0, "lon": body["lon"] ?? 0,
                    "label": body["label"] ?? "", "description": body["description"] ?? NSNull(),
                    "category": body["category"] ?? "anders", "visibility": "private", "public_status": "none",
                    "created_at": now, "owner": ["id": DebugFakeBackend.user.id, "display_name": DebugFakeBackend.user.displayName],
                ]
                spots.insert(new, at: 0)
                return reply(url, 200, new)
            default:
                break
            }
            guard let i = spots.firstIndex(where: { $0["id"] as? String == parts[2] }) else { return reply(url, 404, ["detail": "spot not found"]) }
            guard (spots[i]["owner"] as? [String: Any])?["id"] as? String == DebugFakeBackend.user.id else {
                return reply(url, 403, ["detail": "not your spot"])
            }
            switch (method, parts.count > 3 ? parts[3] : "") {
            case ("PATCH", ""):
                for k in ["label", "description", "category"] { if let v = body[k] { spots[i][k] = v } }
                return reply(url, 200, spots[i])
            case ("DELETE", ""):
                spots.remove(at: i)
                return reply(url, 200, ["ok": true])
            case ("POST", "request-public"):
                if spots[i]["public_status"] as? String == "approved" { return reply(url, 409, ["detail": "already approved"]) }
                spots[i]["visibility"] = "public"; spots[i]["public_status"] = "requested"
                return reply(url, 200, spots[i])
            case ("POST", "revoke-public"):
                spots[i]["visibility"] = "private"; spots[i]["public_status"] = "revoked"
                return reply(url, 200, spots[i])
            default:
                return reply(url, 405, ["detail": "method not allowed"])
            }
        }
    }

    private func reply(_ url: URL, _ status: Int, _ json: Any) -> (Data, HTTPURLResponse) {
        let data = (try? JSONSerialization.data(withJSONObject: json)) ?? Data()
        return (data, HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!)
    }
}

extension SpotsModel {
    /// `-BankjesSpots list | add | detail:<id> | request:<id>`: open that sheet once the Spots are loaded
    /// (`request:` then requests public listing through the normal write path).
    func applyDebugLaunchArguments() async {
        guard let v = UserDefaults.standard.string(forKey: "BankjesSpots") else { return }
        try? await Task.sleep(for: .seconds(1.5))
        if v == "list" { sheet = .list }
        else if v == "add" { sheet = .add(mapCentre) }
        else if v.hasPrefix("detail:") { sheet = .detail(String(v.dropFirst(7))) }
        else if v.hasPrefix("request:"), let s = spot(String(v.dropFirst(8))) {
            // Runs the real write path (SpotsModel → APIClient → the fake) and shows the result.
            sheet = .detail(s.id)
            try? await Task.sleep(for: .seconds(1))
            _ = await requestPublic(s)
        }
    }
}
#endif
