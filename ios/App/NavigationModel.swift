import BankjesCore
import Foundation
import MapKit
import Observation
import UIKit

/// Navigation to one bench: idle → preview → navigating → arrived (spec "Navigation design"). The live loop
/// is `RouteFollower`; this model does the I/O around it (route requests, speech, location, idle timer).
@MainActor @Observable
final class NavigationModel {
    enum Phase: Equatable {
        case idle
        /// Fetching the first route (or a mode change).
        case loading
        case preview
        case failed(RouteProblem)
        case navigating
        case arrived
    }

    private(set) var phase: Phase = .idle
    private(set) var bench: Bench?
    private(set) var route: Route?
    /// Where the previewed route starts; nil until a location fix (then no Start button, as on the web).
    private(set) var origin: Coordinate?
    private(set) var originIsLive = false
    private(set) var follower: RouteFollower?
    /// Bumped on every new route, so the map redraws the line and refits only then.
    private(set) var routeVersion = 0
    /// Bumped on every navigation fix, so the map follows.
    private(set) var fixCount = 0
    private(set) var rerouting = false

    var mode: TravelMode {
        didSet { UserDefaults.standard.set(mode.rawValue, forKey: "bj-nav-mode") }
    }
    var voiceOn: Bool {
        didSet {
            UserDefaults.standard.set(voiceOn, forKey: "bj-nav-voice")
            if !voiceOn { speaker.stop() }
        }
    }

    private let client: APIClient
    private let location: LocationProvider
    private let speaker = Speaker()
    private var loadTask: Task<Void, Never>?

    init(client: APIClient, location: LocationProvider) {
        self.client = client
        self.location = location
        mode = UserDefaults.standard.string(forKey: "bj-nav-mode").flatMap(TravelMode.init(rawValue:)) ?? .foot
        voiceOn = UserDefaults.standard.object(forKey: "bj-nav-voice") as? Bool ?? true
    }

    var isActive: Bool { phase != .idle }
    var showsSheet: Bool {
        switch phase {
        case .loading, .preview, .failed: return true
        case .idle, .navigating, .arrived: return false
        }
    }

    // MARK: preview

    /// A route asked for from the near-me sheet; opened once that sheet has gone (two sheets cannot swap at once).
    @ObservationIgnored var queued: Bench?
    func openQueued() {
        if let b = queued { queued = nil; preview(b) }
    }

    /// Open the preview for a bench: wait briefly for a fix (web: getCurrentPosition, 5 s), then fetch.
    func preview(_ bench: Bench) {
        stop()
        self.bench = bench
        phase = .loading
        location.start()
        loadTask = Task { [weak self] in
            guard let self else { return }
            for _ in 0..<20 where self.location.location == nil && !self.location.isDenied {
                try? await Task.sleep(for: .milliseconds(250))
            }
            await self.loadRoute()
        }
    }

    func setMode(_ m: TravelMode) {
        guard m != mode || phase != .preview else { return }
        mode = m
        guard bench != nil, phase != .navigating else { return }
        phase = .loading
        loadTask?.cancel()
        loadTask = Task { [weak self] in await self?.loadRoute() }
    }

    func retry() {
        guard bench != nil else { return }
        phase = .loading
        loadTask = Task { [weak self] in await self?.loadRoute() }
    }

    private func loadRoute() async {
        guard let bench else { return }
        let live = location.location
        // Without a fix the route is drawn from the Dam (the app's "near me" fallback); Start stays hidden.
        let from = live ?? .dam
        let m = mode
        do {
            let r = try await client.route(from: from, to: bench.coordinate, mode: m)
            guard !Task.isCancelled, self.bench == bench, m == mode else { return }
            origin = from; originIsLive = live != nil
            route = r; routeVersion += 1
            phase = .preview
        } catch {
            guard !Task.isCancelled, self.bench == bench else { return }
            origin = from; originIsLive = live != nil
            route = nil; routeVersion += 1
            phase = .failed(RouteProblem(error, mode: m))
        }
    }

    // MARK: live

    var canStart: Bool { phase == .preview && originIsLive && route != nil && location.isAuthorized }

    func start() {
        guard canStart, let route, let bench else { return }
        follower = RouteFollower(route: route, mode: mode, destination: bench.coordinate)
        phase = .navigating
        UIApplication.shared.isIdleTimerDisabled = true
        location.onNavigationFix = { [weak self] c, at in self?.onFix(c, at: at) }
        location.setNavigating(true)
        if let first = route.steps.first { say(first.instruction) }
    }

    private func onFix(_ c: Coordinate, at: Date) {
        guard phase == .navigating, var f = follower else { return }
        let events = f.onFix(c, at: at)
        follower = f
        fixCount += 1
        for e in events {
            switch e {
            case .advance(_, let text): say(text)
            case .reroute(let from):
                say("Route wordt opnieuw berekend")
                reroute(from: from)
            case .arrived: arrive()
            }
        }
    }

    /// One new route from here (web `navReroute`). A failure is silent: the next off-route fix retries.
    private func reroute(from: Coordinate) {
        guard let bench, !rerouting else { return }
        rerouting = true
        let m = mode
        Task { [weak self] in
            guard let self else { return }
            defer { self.rerouting = false }
            guard let r = try? await self.client.route(from: from, to: bench.coordinate, mode: m),
                  self.phase == .navigating else { return }
            self.follower?.replaceRoute(r)
            self.route = r
            self.routeVersion += 1
        }
    }

    private func arrive() {
        phase = .arrived
        say("Je bent er. Geniet van het bankje!")
        endLive()
    }

    private func endLive() {
        location.setNavigating(false)
        UIApplication.shared.isIdleTimerDisabled = false
    }

    private func say(_ text: String) {
        NSLog("[bankjes-nav] prompt: %@", text)
        if voiceOn { speaker.speak(text) }
    }

    /// Close everything (Stop, Klaar, ×).
    func stop() {
        loadTask?.cancel(); loadTask = nil
        if phase == .navigating { endLive() }
        if phase != .arrived { speaker.stop() }
        phase = .idle
        bench = nil; route = nil; follower = nil; origin = nil
        routeVersion += 1
    }

    // MARK: Open in Kaarten (the escape hatch on 429/503)

    func openInMaps() {
        guard let bench else { return }
        let dest = MKMapItem(placemark: MKPlacemark(coordinate: CLLocationCoordinate2D(latitude: bench.coordinate.lat, longitude: bench.coordinate.lon)))
        dest.name = BenchText.title(bench)
        let dirMode = mode == .bike ? MKLaunchOptionsDirectionsModeCycling : MKLaunchOptionsDirectionsModeWalking
        MKMapItem.openMaps(with: [MKMapItem.forCurrentLocation(), dest], launchOptions: [MKLaunchOptionsDirectionsModeKey: dirMode])
    }
}
