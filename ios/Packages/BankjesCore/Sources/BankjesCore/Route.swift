import Foundation

/// How you travel to a bench. The raw values are `/api/route`'s `mode` (the web app's profiles).
public enum TravelMode: String, CaseIterable, Sendable, Codable {
    case foot, bike, wheelchair

    /// Step advance distance (web `NAV_ADVANCE_M`): the next step starts within this many metres of its
    /// maneuver point.
    public var advanceMetres: Double {
        switch self {
        case .foot, .wheelchair: return 20
        case .bike: return 30
        }
    }
}

/// One instruction of a route (`steps[]` in the `/api/route` contract).
public struct RouteStep: Hashable, Sendable {
    /// Dutch, from the server (ORS text, or the OSRM table in app/routing.py).
    public let instruction: String
    public let distanceM: Double
    public let durationS: Double
    public let maneuverPoint: Coordinate
    /// Index into `Route.geometry` where this step starts.
    public let geometryIdx: Int
    public let type: Int

    public init(instruction: String, distanceM: Double, durationS: Double, maneuverPoint: Coordinate, geometryIdx: Int, type: Int = -1) {
        self.instruction = instruction; self.distanceM = distanceM; self.durationS = durationS
        self.maneuverPoint = maneuverPoint; self.geometryIdx = geometryIdx; self.type = type
    }
}

/// `GET /api/route`: `{engine, geometry [[lat,lon]…], distance_m, duration_s, steps[…]}`.
public struct Route: Hashable, Sendable {
    /// "ors" or "osrm" (which upstream the server used).
    public let engine: String
    public let geometry: [Coordinate]
    public let distanceM: Double
    public let durationS: Double
    public let steps: [RouteStep]
    /// Cumulative metres along `geometry` (web `navCumulative`); same length as `geometry`.
    public let cumulative: [Double]

    public init(engine: String, geometry: [Coordinate], distanceM: Double, durationS: Double, steps: [RouteStep]) {
        self.engine = engine; self.geometry = geometry; self.distanceM = distanceM; self.durationS = durationS
        self.steps = steps
        var cum: [Double] = geometry.isEmpty ? [] : [0]
        for i in geometry.indices.dropFirst() { cum.append(cum[i - 1] + Geo.distance(geometry[i - 1], geometry[i])) }
        cumulative = cum
    }

    public static func decode(_ data: Data) throws -> Route {
        try JSONDecoder().decode(Route.self, from: data)
    }
}

extension Route: Decodable {
    private enum Keys: String, CodingKey { case engine, geometry, distance_m, duration_s, steps }
    private enum StepKeys: String, CodingKey { case instruction, distance_m, duration_s, maneuver_point, geometry_idx, type }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        let pairs = try c.decode([[Double]].self, forKey: .geometry)
        guard pairs.count >= 2, pairs.allSatisfy({ $0.count >= 2 }) else {
            throw DecodingError.dataCorruptedError(forKey: .geometry, in: c, debugDescription: "geometry needs ≥ 2 [lat,lon] points")
        }
        let geometry = pairs.map { Coordinate(lat: $0[0], lon: $0[1]) }
        var stepsC = try c.nestedUnkeyedContainer(forKey: .steps)
        var steps: [RouteStep] = []
        while !stepsC.isAtEnd {
            let s = try stepsC.nestedContainer(keyedBy: StepKeys.self)
            let mp = try s.decode([Double].self, forKey: .maneuver_point)
            guard mp.count >= 2 else {
                throw DecodingError.dataCorruptedError(forKey: .maneuver_point, in: s, debugDescription: "maneuver_point is [lat,lon]")
            }
            let idx = try s.decode(Int.self, forKey: .geometry_idx)
            steps.append(RouteStep(
                instruction: (try? s.decode(String.self, forKey: .instruction)) ?? "",
                distanceM: (try? s.decode(Double.self, forKey: .distance_m)) ?? 0,
                durationS: (try? s.decode(Double.self, forKey: .duration_s)) ?? 0,
                maneuverPoint: Coordinate(lat: mp[0], lon: mp[1]),
                geometryIdx: min(max(idx, 0), geometry.count - 1),
                type: (try? s.decode(Int.self, forKey: .type)) ?? -1))
        }
        self.init(engine: (try? c.decode(String.self, forKey: .engine)) ?? "?",
                  geometry: geometry,
                  distanceM: try c.decode(Double.self, forKey: .distance_m),
                  durationS: try c.decode(Double.self, forKey: .duration_s),
                  steps: steps)
    }
}

/// Why a route could not be shown, sorted by what the UI offers (spec "Navigation design", Errors).
public enum RouteProblem: Equatable, Sendable {
    /// 400: a point lies outside the service area (50 km around Amsterdam).
    case outsideArea
    /// 429: the server's daily routing budget is spent. Offer "Open in Kaarten".
    case budget
    /// 503 on wheelchair: no ORS profile on this server. Show the server's `detail`.
    case wheelchairUnavailable(detail: String?)
    /// Any other 503 / 5xx: offer "Open in Kaarten".
    case unavailable(detail: String?)
    /// No network: offer a retry.
    case offline
    /// Anything else (a bad body, an unexpected status).
    case other(String)

    public init(_ error: Error, mode: TravelMode) {
        switch error as? APIError {
        case .http(400, _)?: self = .outsideArea
        case .http(429, _)?: self = .budget
        case .http(503, let d)? where mode == .wheelchair: self = .wheelchairUnavailable(detail: d)
        case .http(let s, let d)? where s >= 500: self = .unavailable(detail: d)
        case .http(let s, _)?: self = .other("HTTP \(s)")
        case .transport?: self = .offline
        case .decoding(let m)?: self = .other(m)
        case nil: self = .other(String(describing: error))
        }
    }

    /// Show "Open in Kaarten" as the escape hatch.
    public var offersMaps: Bool {
        switch self {
        case .budget, .unavailable, .offline, .other: return true
        case .outsideArea, .wheelchairUnavailable: return false
        }
    }

    /// Show "Opnieuw proberen".
    public var offersRetry: Bool {
        switch self {
        case .offline, .unavailable, .other: return true
        case .outsideArea, .budget, .wheelchairUnavailable: return false
        }
    }
}

extension APIClient {
    public func routeRequest(from: Coordinate, to: Coordinate, mode: TravelMode) -> URLRequest {
        var comps = URLComponents(url: environment.apiBase.appending(path: "api/route"), resolvingAgainstBaseURL: false)!
        comps.queryItems = [
            URLQueryItem(name: "from_lat", value: String(from.lat)),
            URLQueryItem(name: "from_lon", value: String(from.lon)),
            URLQueryItem(name: "to_lat", value: String(to.lat)),
            URLQueryItem(name: "to_lon", value: String(to.lon)),
            URLQueryItem(name: "mode", value: mode.rawValue),
        ]
        var req = URLRequest(url: comps.url!)
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        return req
    }

    /// `GET /api/route`. Throws `APIError` (400 outside the area, 429 budget, 503 unavailable / no wheelchair).
    public func route(from: Coordinate, to: Coordinate, mode: TravelMode) async throws -> Route {
        let data = try await get(routeRequest(from: from, to: to, mode: mode))
        do { return try Route.decode(data) } catch { throw APIError.decoding(String(describing: error)) }
    }
}

public enum RouteFormat {
    /// Web `navFmtDur`: "7 min", "1 u 5 min".
    public static func duration(_ seconds: Double) -> String {
        let min = Int((max(0, seconds) / 60).rounded())
        return min < 60 ? "\(min) min" : "\(min / 60) u \(min % 60) min"
    }
}
