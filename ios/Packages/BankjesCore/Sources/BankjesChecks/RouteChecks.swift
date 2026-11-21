// I4 navigation checks: the /api/route contract and a GPS-trace replay through RouteFollower.
// Fixture route-ors.json is a real acc response (GET /api/route, Dam → bench osm:14079171173, mode=foot,
// 2026-11-20). acc has no ORS_API_KEY, so the server answered with its OSRM fallback (engine "osrm");
// the contract is the same for both engines.
import BankjesCore
import Foundation

/// A point `metres` from `p` on a bearing (degrees). Flat-earth is fine at these distances.
func offset(_ p: Coordinate, metres: Double, bearing: Double) -> Coordinate {
    let r = bearing * .pi / 180
    let dLat = metres * cos(r) / 111_195.0
    let dLon = metres * sin(r) / (111_195.0 * cos(p.lat * .pi / 180))
    return Coordinate(lat: p.lat + dLat, lon: p.lon + dLon)
}

/// Points every ≤ `spacing` metres along `geometry[from...to]` (the vertices included).
func densify(_ g: [Coordinate], from: Int, to: Int, spacing: Double = 8) -> [Coordinate] {
    var out: [Coordinate] = [g[from]]
    guard from < to else { return out }
    for i in (from + 1)...to {
        let a = g[i - 1], b = g[i]
        let n = max(1, Int((Geo.distance(a, b) / spacing).rounded(.up)))
        for k in 1...n {
            let t = Double(k) / Double(n)
            out.append(Coordinate(lat: a.lat + (b.lat - a.lat) * t, lon: a.lon + (b.lon - a.lon) * t))
        }
    }
    return out
}

/// What a reroute from the rejoin point would return: the rest of the route, steps re-indexed, a new
/// "Vertrek" first step (as both engines start a route).
func suffixRoute(_ r: Route, from k: Int) -> Route {
    let g = Array(r.geometry[k...])
    var steps = [RouteStep(instruction: "Vertrek", distanceM: 0, durationS: 0, maneuverPoint: g[0], geometryIdx: 0)]
    steps += r.steps.filter { $0.geometryIdx > k }.map {
        RouteStep(instruction: $0.instruction, distanceM: $0.distanceM, durationS: $0.durationS,
                  maneuverPoint: $0.maneuverPoint, geometryIdx: $0.geometryIdx - k, type: $0.type)
    }
    let rest = r.cumulative.last! - r.cumulative[k]
    return Route(engine: r.engine, geometry: g, distanceM: rest, durationS: r.durationS * rest / r.distanceM, steps: steps)
}

func routeChecks(fixtures: URL) {
    // MARK: contract
    let data = try! Data(contentsOf: fixtures.appending(path: "route-ors.json"))
    let route = try! Route.decode(data)
    let bench = Coordinate(lat: 52.3697741, lon: 4.8946051)   // osm:14079171173, the destination
    check(route.engine == "osrm" && route.geometry.count == 40 && route.steps.count == 9, "route fixture: 40 points, 9 steps")
    check(route.distanceM == 522 && route.durationS == 418, "route fixture: 522 m, 418 s")
    check(route.steps.first?.instruction == "Vertrek via Dam" && route.steps.last?.instruction == "Je bestemming is bereikt", "Dutch instructions")
    check(route.steps.map(\.geometryIdx) == [0, 10, 17, 23, 30, 31, 32, 37, 39], "geometry_idx per step")
    check(route.cumulative.count == 40 && abs(route.cumulative.last! - 522) < 10, "cumulative length ≈ distance_m")
    check(Geo.distance(route.geometry.last!, bench) < RouteFollower.arrivalMetres, "route ends within 15 m of the bench")
    check((try? Route.decode(Data(#"{"geometry":[[52,4]],"distance_m":1,"duration_s":1,"steps":[]}"#.utf8))) == nil, "a one-point route is refused")
    check((try? Route.decode(Data(#"{"detail":"x"}"#.utf8))) == nil, "an error body is not a route")
    let clamped = try? Route.decode(Data(#"{"geometry":[[52,4],[52.001,4]],"distance_m":111,"duration_s":80,"steps":[{"instruction":"x","distance_m":1,"duration_s":1,"maneuver_point":[52,4],"geometry_idx":99}]}"#.utf8))
    check(clamped?.steps.first?.geometryIdx == 1 && clamped?.engine == "?", "geometry_idx clamped; engine optional")

    // MARK: client + errors
    let fake = FakeTransport()
    let client = APIClient(environment: .acc, transport: fake)
    let req = client.routeRequest(from: .dam, to: bench, mode: .wheelchair)
    check(req.url?.absoluteString == "https://bankjes-acc.stephensprive.app/api/route?from_lat=52.3731&from_lon=4.8926&to_lat=52.3697741&to_lon=4.8946051&mode=wheelchair", "route URL")
    check(TravelMode.allCases.map(\.rawValue) == ["foot", "bike", "wheelchair"], "modes are the web's profiles")
    fake.reply = (200, data)
    check(run { try? await client.route(from: .dam, to: bench, mode: .foot) } == route, "route() decodes")
    func problem(_ status: Int, _ body: String, _ mode: TravelMode = .foot) -> RouteProblem? {
        fake.reply = (status, Data(body.utf8))
        return run { () -> RouteProblem? in
            do { _ = try await client.route(from: .dam, to: bench, mode: mode); return nil } catch { return RouteProblem(error, mode: mode) }
        }
    }
    // The wheelchair 503 body is acc's real answer on 2026-11-20 (no ORS key there).
    let wc = problem(503, #"{"detail":"rolstoelroute vereist de ORS-dienst (nog niet geconfigureerd)"}"#, .wheelchair)
    check(wc == .wheelchairUnavailable(detail: "rolstoelroute vereist de ORS-dienst (nog niet geconfigureerd)") && wc?.offersMaps == false, "wheelchair 503 → the server's detail")
    let u = problem(503, #"{"detail":"route tijdelijk niet beschikbaar"}"#)
    check(u == .unavailable(detail: "route tijdelijk niet beschikbaar") && u?.offersMaps == true, "foot 503 → Open in Kaarten")
    let b = problem(429, #"{"detail":"dagbudget routing op"}"#)
    check(b == .budget && b?.offersMaps == true && b?.offersRetry == false, "429 → budget, Open in Kaarten")
    check(problem(400, #"{"detail":"buiten servicegebied"}"#) == .outsideArea, "400 → outside the service area")
    if case .other? = problem(200, "<html>") { check(true, "") } else { check(false, "garbage → other") }
    fake.fail = URLError(.notConnectedToInternet)
    check(problem(200, "") == .offline && RouteProblem.offline.offersRetry, "offline → retry")
    fake.fail = nil
    check(RouteFormat.duration(418) == "7 min" && RouteFormat.duration(3900) == "1 u 5 min" && RouteFormat.duration(0) == "0 min", "duration like navFmtDur")

    // MARK: GPS trace replay: Dam → bench on foot, with a 3-fix detour on the Rokin
    // On the route up to vertex 20, three fixes 60 m east of it, back on at vertex 20, then on to the end
    // and 10 m past it (towards the bench). One fix per second.
    let g = route.geometry
    let detourAt = 20
    var trace = densify(g, from: 0, to: detourAt)
    let offFixes = (1...3).map { offset(g[detourAt], metres: 50 + Double($0) * 5, bearing: 90) }
    let firstOff = trace.count
    trace += offFixes
    let rejoin = trace.count
    trace += densify(g, from: detourAt, to: g.count - 1)
    trace.append(bench)

    var f = RouteFollower(route: route, mode: .foot, destination: bench)
    check(abs(f.remaining.metres - route.cumulative.last!) < 0.001 && abs(f.remaining.seconds - 418) < 1, "remaining at the start = whole route")
    check(f.currentStep?.instruction == "Vertrek via Dam" && f.nextStep?.instruction == "Sla linksaf", "starts on step 0")
    let t0 = Date(timeIntervalSince1970: 1_790_000_000)
    var log: [(fix: Int, event: RouteFollower.Event)] = []
    var arrivedAfter: [RouteFollower.Event] = []
    for (i, p) in trace.enumerated() {
        if f.hasArrived { arrivedAfter += f.onFix(p, at: t0 + Double(i)); continue }
        for e in f.onFix(p, at: t0 + Double(i)) {
            log.append((i, e))
            // The app fetches a new route here; the server answers with the rest of the route from the rejoin point.
            if case .reroute = e { f.replaceRoute(suffixRoute(route, from: detourAt)) }
        }
    }
    let reroutes = log.filter { if case .reroute = $0.event { return true }; return false }
    check(reroutes.count == 1, "exactly one reroute (got \(reroutes.count))")
    check(reroutes.first?.fix == firstOff + 2, "the reroute comes on the 3rd off-route fix, not before")
    if case .reroute(let from)? = reroutes.first?.event { check(from == offFixes[2], "reroute from the 3rd off-route fix") }
    let advances = log.compactMap { e -> String? in if case .advance(_, let s) = e.event { return s }; return nil }
    check(advances == Array(route.steps.dropFirst().map(\.instruction)), "every step advances once, in order: \(advances)")
    check(log.filter { if case .advance = $0.event { return $0.fix >= firstOff && $0.fix < rejoin }; return false }.isEmpty, "no advance while off-route")
    let arrivals = log.filter { $0.event == .arrived }
    check(arrivals.count == 1, "one arrival")
    if let a = arrivals.first {
        check(Geo.distance(trace[a.fix], bench) < 15 && Geo.distance(trace[a.fix - 1], bench) >= 15, "arrival at the first fix within 15 m (\(Geo.distance(trace[a.fix], bench)) m; before: \(Geo.distance(trace[a.fix - 1], bench)) m)")
        check(log.last?.event == .arrived, "arrival is the last event")
    }
    check(f.hasArrived && arrivedAfter.isEmpty, "fixes after arrival are ignored")
    check(f.remaining.metres < 15, "nothing left to walk at the end")

    // Arrival boundary: 16 m out is not there yet, 14.9 m is.
    let approachRoute = Route(engine: "t", geometry: [offset(bench, metres: 100, bearing: 0), bench], distanceM: 100, durationS: 80,
                              steps: [RouteStep(instruction: "Vertrek", distanceM: 100, durationS: 80, maneuverPoint: offset(bench, metres: 100, bearing: 0), geometryIdx: 0)])
    var a = RouteFollower(route: approachRoute, mode: .foot, destination: bench)
    check(a.onFix(offset(bench, metres: 16, bearing: 0), at: t0).isEmpty, "16 m: not arrived")
    check(a.onFix(offset(bench, metres: 15.05, bearing: 0), at: t0 + 1).isEmpty, "15.05 m: not arrived")
    check(a.onFix(offset(bench, metres: 14.9, bearing: 0), at: t0 + 2) == [.arrived], "14.9 m: arrived")

    // Off-route: two fixes away and back resets the count; a reroute needs 3 in a row.
    var o = RouteFollower(route: route, mode: .foot, destination: bench)
    let away = offset(g[0], metres: 60, bearing: 270)
    _ = o.onFix(away, at: t0); _ = o.onFix(away, at: t0 + 1)
    check(o.offCount == 2, "two off-route fixes counted")
    _ = o.onFix(g[0], at: t0 + 2)
    check(o.offCount == 0, "back on the route resets the count")
    check(o.onFix(offset(g[0], metres: 39, bearing: 270), at: t0 + 3).isEmpty && o.offCount == 0, "39 m away is still on the route")
    _ = o.onFix(away, at: t0 + 4); _ = o.onFix(away, at: t0 + 5)
    check(o.onFix(away, at: t0 + 6) == [.reroute(from: away)] && o.offCount == 0, "3rd off-route fix → reroute")
    // The reroute failed (offline): no new route. More off-route fixes within 10 s do not reroute again.
    check((7...9).allSatisfy { o.onFix(away, at: t0 + Double($0)).isEmpty }, "no second reroute within 10 s")
    check(o.onFix(away, at: t0 + 16).isEmpty, "exactly 10 s later: still waiting (web: > 10 s)")
    check(o.onFix(away, at: t0 + 17) == [.reroute(from: away)], "the next off-route fix after 10 s retries")

    // Step advance distance per mode: 20 m on foot, 30 m by bike.
    let near1 = g[1]
    let d1 = Geo.distance(near1, route.steps[1].maneuverPoint)
    check(d1 > 20 && d1 < 30, "precondition: vertex 1 is 20–30 m from step 1 (\(d1) m)")
    var foot = RouteFollower(route: route, mode: .foot, destination: bench)
    var bike = RouteFollower(route: route, mode: .bike, destination: bench)
    check(foot.onFix(near1, at: t0).isEmpty, "foot: \(Int(d1)) m before the turn is too early")
    check(bike.onFix(near1, at: t0) == [.advance(stepIdx: 1, instruction: "Sla linksaf")], "bike: \(Int(d1)) m before the turn advances")
    // Passing a step's geometry_idx advances it even when its point is far (a skipped GPS fix).
    var skip = RouteFollower(route: route, mode: .foot, destination: bench)
    let jumped = skip.onFix(g[24], at: t0)
    check(jumped.map { if case .advance(let i, _) = $0 { return i }; return -1 } == [1, 2, 3], "a jump past three steps advances all three")
    check(skip.currentStep?.instruction == "Sla rechtsaf naar Rokin" && skip.metresToNextStep != nil, "now on the Rokin")
    check(skip.remaining.metres < route.cumulative.last! - route.cumulative[23], "remaining drops as you go")
}
