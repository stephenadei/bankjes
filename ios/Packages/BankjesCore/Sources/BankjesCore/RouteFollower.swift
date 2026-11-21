import Foundation

/// The live turn-by-turn loop, a direct port of the web app's `navNearestOnRoute`, `navOnFix` and
/// `navRemaining` (app/static/index.html). Pure: feed it fixes, act on the events it returns. The caller
/// does the I/O (speech, the reroute request) and hands a fresh route back with `replaceRoute(_:)`.
public struct RouteFollower: Sendable {
    public enum Event: Equatable, Sendable {
        /// The next step started; speak its instruction.
        case advance(stepIdx: Int, instruction: String)
        /// Fetch a new route from this fix ("Route wordt opnieuw berekend"). At most one per `rerouteInterval`.
        case reroute(from: Coordinate)
        /// Within `arrivalMetres` of the destination; the follower ignores fixes from now on.
        case arrived
    }

    // Thresholds from the web app (spec "Findings": off-route 40 m × 3 fixes, reroute ≤ 1 per 10 s, arrival 15 m).
    public static let offRouteMetres = 40.0
    public static let offRouteFixes = 3
    public static let rerouteInterval: TimeInterval = 10
    public static let arrivalMetres = 15.0
    /// Nearest-point search window around the current index (curIdx −5 … +60).
    static let windowBack = 5, windowAhead = 60

    public private(set) var route: Route
    public let mode: TravelMode
    /// The bench itself (arrival is measured to the bench, not to the end of the route).
    public let destination: Coordinate
    public private(set) var stepIdx = 0
    public private(set) var curIdx = 0
    public private(set) var offCount = 0
    public private(set) var lastReroute: Date?
    public private(set) var lastFix: Coordinate?
    /// Distance from the last fix to the nearest point on the route.
    public private(set) var offsetMetres: Double = 0
    public private(set) var hasArrived = false

    public init(route: Route, mode: TravelMode, destination: Coordinate) {
        self.route = route; self.mode = mode; self.destination = destination
    }

    /// Nearest route point within the window around `curIdx` (web `navNearestOnRoute`).
    public func nearestOnRoute(_ p: Coordinate) -> (idx: Int, dist: Double) {
        let g = route.geometry
        guard !g.isEmpty else { return (0, .infinity) }
        let from = max(0, curIdx - Self.windowBack), to = min(g.count - 1, curIdx + Self.windowAhead)
        var best = (idx: curIdx, dist: Double.infinity)
        for i in from...max(from, to) {
            let d = Geo.distance(p, g[i])
            if d < best.dist { best = (i, d) }
        }
        return best
    }

    /// One location fix (web `navOnFix`). Returns what happened, in order.
    public mutating func onFix(_ p: Coordinate, at now: Date) -> [Event] {
        guard !hasArrived else { return [] }
        lastFix = p
        let near = nearestOnRoute(p)
        offsetMetres = near.dist
        curIdx = max(curIdx, near.idx)

        // Off-route → one reroute (at most one per 10 s). The web returns here and skips the rest of the fix.
        if near.dist > Self.offRouteMetres {
            offCount += 1
            if offCount >= Self.offRouteFixes, lastReroute.map({ now.timeIntervalSince($0) > Self.rerouteInterval }) ?? true {
                lastReroute = now
                offCount = 0
                return [.reroute(from: p)]
            }
        } else {
            offCount = 0
        }

        var events: [Event] = []
        let steps = route.steps
        while stepIdx < steps.count - 1 {
            let next = steps[stepIdx + 1]
            if curIdx >= next.geometryIdx || Geo.distance(p, next.maneuverPoint) < mode.advanceMetres {
                stepIdx += 1
                events.append(.advance(stepIdx: stepIdx, instruction: next.instruction))
            } else { break }
        }

        if Geo.distance(p, destination) < Self.arrivalMetres {
            hasArrived = true
            events.append(.arrived)
        }
        return events
    }

    /// A rerouted route from the server (web `navReroute`): start over at its first step.
    public mutating func replaceRoute(_ new: Route) {
        route = new
        stepIdx = 0
        curIdx = 0
        offCount = 0
    }

    /// The step being followed now.
    public var currentStep: RouteStep? { route.steps.isEmpty ? nil : route.steps[min(stepIdx, route.steps.count - 1)] }
    /// The step after it (shown as "over 80 m: …").
    public var nextStep: RouteStep? { stepIdx + 1 < route.steps.count ? route.steps[stepIdx + 1] : nil }
    /// Metres from the last fix to the next maneuver.
    public var metresToNextStep: Double? {
        guard let n = nextStep, let f = lastFix else { return nil }
        return Geo.distance(f, n.maneuverPoint)
    }

    /// Remaining metres along the route and seconds at the route's own pace (web `navRemaining`).
    public var remaining: (metres: Double, seconds: Double) {
        let cum = route.cumulative
        guard let total = cum.last else { return (0, 0) }
        let done = cum[min(curIdx, cum.count - 1)]
        let m = max(0, total - done)
        let s = route.distanceM > 0 ? m / route.distanceM * route.durationS : 0
        return (m, s)
    }
}
