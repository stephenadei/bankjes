import Foundation

// I6 Spots (Plekjes): the user's own places plus approved public ones. Contract: spec
// docs/specs/2026-11-20-ios-app.md rows 7–12 and the backend's app/spots.py + app/spots_repo.py.
// Writes are online only: every method sends exactly one request and nothing is queued or retried.

/// `category`: the backend's `CATEGORIES` tuple, in its order.
public enum SpotCategory: String, CaseIterable, Codable, Sendable {
    case bank, stoel, picknicktafel, krukje, anders
}

/// `public_status`: the `spots.public_status` CHECK constraint. `unknown` keeps a future value from
/// breaking the list.
public enum SpotPublicStatus: String, Sendable, CaseIterable {
    case none, requested, approved, denied, revoked, unknown
}

/// `visibility`: `private / friends / public` (friends is schema-only in v1).
public enum SpotVisibility: String, Sendable {
    case `private`, friends, `public`, unknown
}

/// One Spot as `GET /api/spots` and every write return it:
/// `{id, lat, lon, label, description, category, visibility, public_status, created_at, owner:{id, display_name}}`.
public struct Spot: Identifiable, Hashable, Sendable {
    public struct Owner: Hashable, Sendable {
        public let id: String
        public let displayName: String?
        public init(id: String, displayName: String?) { self.id = id; self.displayName = displayName }
    }

    public let id: String
    public let coordinate: Coordinate
    public let label: String
    public let description: String?
    /// nil when the server sends a category this build does not know (shown as "anders").
    public let category: SpotCategory?
    public let visibility: SpotVisibility
    public let publicStatus: SpotPublicStatus
    /// SQLite `CURRENT_TIMESTAMP` text ("2026-11-20 10:00:00", UTC), kept as sent.
    public let createdAt: String?
    public let owner: Owner

    public init(id: String, coordinate: Coordinate, label: String, description: String?, category: SpotCategory?,
                visibility: SpotVisibility, publicStatus: SpotPublicStatus, createdAt: String?, owner: Owner) {
        self.id = id; self.coordinate = coordinate; self.label = label; self.description = description
        self.category = category; self.visibility = visibility; self.publicStatus = publicStatus
        self.createdAt = createdAt; self.owner = owner
    }

    public func isOwned(by userId: String?) -> Bool { userId != nil && owner.id == userId }

    /// What anyone may see: listed publicly and approved by an admin.
    public var isPublicApproved: Bool { visibility == .public && publicStatus == .approved }

    /// "Openbaar maken aanvragen" is offered for none / denied / revoked (the backend 409s on approved;
    /// re-requesting while requested is a no-op, so it is not offered).
    public var canRequestPublic: Bool { [.none, .denied, .revoked].contains(publicStatus) }
    /// "Openbaar intrekken" is offered while a request is pending or the Spot is listed.
    public var canRevokePublic: Bool { publicStatus == .requested || publicStatus == .approved || visibility == .public }
}

extension Spot: Decodable {
    private enum Keys: String, CodingKey {
        case id, lat, lon, label, description, category, visibility, owner
        case publicStatus = "public_status", createdAt = "created_at"
    }
    private enum OwnerKeys: String, CodingKey { case id, displayName = "display_name" }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        let id = try c.decode(String.self, forKey: .id)
        let lat = try c.decode(Double.self, forKey: .lat), lon = try c.decode(Double.self, forKey: .lon)
        guard !id.isEmpty, (-90...90).contains(lat), (-180...180).contains(lon) else {
            throw DecodingError.dataCorruptedError(forKey: .id, in: c, debugDescription: "bad id or coordinate")
        }
        let o = try c.nestedContainer(keyedBy: OwnerKeys.self, forKey: .owner)
        let owner = Owner(id: try o.decode(String.self, forKey: .id),
                          displayName: (try? o.decodeIfPresent(String.self, forKey: .displayName)).flatMap { $0 })
        func text(_ k: Keys) -> String? { (try? c.decodeIfPresent(String.self, forKey: k)).flatMap { $0 } }
        self.init(id: id, coordinate: Coordinate(lat: lat, lon: lon),
                  label: try c.decode(String.self, forKey: .label),
                  description: text(.description),
                  category: text(.category).flatMap(SpotCategory.init(rawValue:)),
                  visibility: text(.visibility).flatMap(SpotVisibility.init(rawValue:)) ?? .unknown,
                  publicStatus: text(.publicStatus).flatMap(SpotPublicStatus.init(rawValue:)) ?? .unknown,
                  createdAt: text(.createdAt), owner: owner)
    }
}

/// `{spots:[Spot]}`. A row that does not decode is dropped; the rest stays.
public struct SpotsResponse: Decodable, Sendable {
    public let spots: [Spot]
    private struct Lenient: Decodable {
        let spot: Spot?
        init(from decoder: Decoder) throws { spot = try? Spot(from: decoder) }
    }
    private enum Keys: String, CodingKey { case spots }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        spots = try c.decode([Lenient].self, forKey: .spots).compactMap(\.spot)
    }
    public static func decode(_ data: Data) throws -> SpotsResponse { try JSONDecoder().decode(SpotsResponse.self, from: data) }
}

/// The ACL `GET /api/spots` applies (spots_repo.ACL_VISIBLE_WHERE), applied again on the device: public +
/// approved, plus your own. Another user's private (or pending) Spot never reaches the map or the list,
/// even if a server or cache ever sent one.
public enum SpotFilter {
    public static func visible(_ spots: [Spot], to userId: String?) -> [Spot] {
        spots.filter { $0.isOwned(by: userId) || $0.isPublicApproved }
    }
    public static func own(_ spots: [Spot], userId: String?) -> [Spot] {
        spots.filter { $0.isOwned(by: userId) }
    }
}

/// The form's input, checked against the backend's pydantic rules before anything is sent:
/// label 1–60 after trim, description ≤ 400, category in `CATEGORIES`.
public struct SpotDraft: Equatable, Sendable {
    public var label: String
    public var description: String
    public var category: SpotCategory

    public static let labelMax = 60
    public static let descriptionMax = 400

    public enum Problem: Equatable, Sendable { case labelEmpty, labelTooLong, descriptionTooLong }

    public init(label: String = "", description: String = "", category: SpotCategory = .bank) {
        self.label = label; self.description = description; self.category = category
    }
    public init(_ spot: Spot) {
        self.init(label: spot.label, description: spot.description ?? "", category: spot.category ?? .anders)
    }

    public var trimmedLabel: String { label.trimmingCharacters(in: .whitespacesAndNewlines) }
    public var trimmedDescription: String { description.trimmingCharacters(in: .whitespacesAndNewlines) }

    public var problems: [Problem] {
        var p: [Problem] = []
        if trimmedLabel.isEmpty { p.append(.labelEmpty) }
        if trimmedLabel.count > Self.labelMax { p.append(.labelTooLong) }
        if trimmedDescription.count > Self.descriptionMax { p.append(.descriptionTooLong) }
        return p
    }
    public var isValid: Bool { problems.isEmpty }

    /// `POST /api/spots` body. An empty description is left out (the server stores NULL).
    public func createBody(at c: Coordinate) -> [String: Any] {
        var b: [String: Any] = ["lat": c.lat, "lon": c.lon, "label": trimmedLabel, "category": category.rawValue]
        if !trimmedDescription.isEmpty { b["description"] = trimmedDescription }
        return b
    }

    /// `PATCH /api/spots/{id}` body: only what changed. A cleared description is sent as "" (the server
    /// ignores null, so null could never clear it).
    public func patchBody(from spot: Spot) -> [String: Any] {
        var b: [String: Any] = [:]
        if trimmedLabel != spot.label { b["label"] = trimmedLabel }
        if trimmedDescription != (spot.description ?? "") { b["description"] = trimmedDescription }
        if category != spot.category { b["category"] = category.rawValue }
        return b
    }
}

// MARK: - Endpoints

extension APIClient {
    private func spotsURL(_ parts: String...) -> URL {
        parts.reduce(environment.apiBase.appending(path: "api/spots")) { $0.appending(path: $1) }
    }

    private func jsonRequest(_ method: String, _ url: URL, body: [String: Any]?) -> URLRequest {
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try? JSONSerialization.data(withJSONObject: body, options: [.sortedKeys])
        }
        return req
    }

    public func spotsRequest() -> URLRequest { jsonRequest("GET", spotsURL(), body: nil) }
    public func createSpotRequest(_ draft: SpotDraft, at c: Coordinate) -> URLRequest {
        jsonRequest("POST", spotsURL(), body: draft.createBody(at: c))
    }
    public func updateSpotRequest(_ spot: Spot, with draft: SpotDraft) -> URLRequest {
        jsonRequest("PATCH", spotsURL(spot.id), body: draft.patchBody(from: spot))
    }
    public func deleteSpotRequest(id: String) -> URLRequest { jsonRequest("DELETE", spotsURL(id), body: nil) }
    public func requestPublicRequest(id: String) -> URLRequest { jsonRequest("POST", spotsURL(id, "request-public"), body: nil) }
    public func revokePublicRequest(id: String) -> URLRequest { jsonRequest("POST", spotsURL(id, "revoke-public"), body: nil) }

    private func decodeSpot(_ data: Data) throws -> Spot {
        do { return try JSONDecoder().decode(Spot.self, from: data) } catch { throw APIError.decoding("spot") }
    }

    /// `GET /api/spots` (Bearer optional): public + approved, plus all your own; filtered again on the device.
    public func spots() async throws -> [Spot] {
        let data = try await get(spotsRequest())
        let all: [Spot]
        do { all = try SpotsResponse.decode(data).spots } catch { throw APIError.decoding("spots") }
        return SpotFilter.visible(all, to: session?.user?.id)
    }

    /// `POST /api/spots`. Private, `public_status` none.
    public func createSpot(_ draft: SpotDraft, at c: Coordinate) async throws -> Spot {
        try decodeSpot(try await get(createSpotRequest(draft, at: c)))
    }

    /// `PATCH /api/spots/{id}` with only the changed fields; nothing changed → no request, the Spot back.
    public func updateSpot(_ spot: Spot, with draft: SpotDraft) async throws -> Spot {
        if draft.patchBody(from: spot).isEmpty { return spot }
        return try decodeSpot(try await get(updateSpotRequest(spot, with: draft)))
    }

    /// `DELETE /api/spots/{id}` → `{ok:true}`.
    public func deleteSpot(id: String) async throws {
        let data = try await get(deleteSpotRequest(id: id))
        guard (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["ok"] as? Bool == true else {
            throw APIError.decoding("delete")
        }
    }

    /// `POST /api/spots/{id}/request-public` → `visibility=public, public_status=requested`; 409 if approved.
    public func requestPublic(id: String) async throws -> Spot { try decodeSpot(try await get(requestPublicRequest(id: id))) }

    /// `POST /api/spots/{id}/revoke-public` → `visibility=private, public_status=revoked`.
    public func revokePublic(id: String) async throws -> Spot { try decodeSpot(try await get(revokePublicRequest(id: id))) }
}
