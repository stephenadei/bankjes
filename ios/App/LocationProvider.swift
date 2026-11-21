import BankjesCore
import CoreLocation
import Observation

/// When-In-Use location for "near me" and navigation. Never asks for "Always".
@MainActor @Observable
final class LocationProvider: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private(set) var authorization: CLAuthorizationStatus
    private(set) var location: Coordinate?
    /// True between `setNavigating(true)` and `setNavigating(false)`.
    private(set) var isNavigating = false
    /// Navigation's per-fix callback. Called directly from the delegate (not through SwiftUI), so it keeps
    /// running with the screen locked.
    @ObservationIgnored var onNavigationFix: ((Coordinate, Date) -> Void)?

    override init() {
        authorization = manager.authorizationStatus
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyNearestTenMeters
        manager.distanceFilter = 20
    }

    var isDenied: Bool { authorization == .denied || authorization == .restricted }
    var isAuthorized: Bool { authorization == .authorizedWhenInUse || authorization == .authorizedAlways }

    /// Asks once (iOS shows the prompt only while undetermined), then follows the user while the list is open.
    func start() {
        if authorization == .notDetermined { manager.requestWhenInUseAuthorization() }
        if isAuthorized { manager.startUpdatingLocation() }
    }

    /// Stops updates, unless navigation is running (closing the near-me list must not stop guidance).
    func stop() { if !isNavigating { manager.stopUpdatingLocation() } }

    /// Decision D2: while navigating, best accuracy, `.fitness`, every fix, and background updates on (needs
    /// `UIBackgroundModes: [location]`; still When-In-Use, so iOS shows the blue indicator). Off again after.
    func setNavigating(_ on: Bool) {
        guard on != isNavigating else { return }
        isNavigating = on
        if on {
            manager.desiredAccuracy = kCLLocationAccuracyBest
            manager.activityType = .fitness
            manager.distanceFilter = kCLDistanceFilterNone
            manager.pausesLocationUpdatesAutomatically = false
            manager.allowsBackgroundLocationUpdates = true
            manager.showsBackgroundLocationIndicator = true
            manager.startUpdatingLocation()
        } else {
            onNavigationFix = nil
            manager.allowsBackgroundLocationUpdates = false
            manager.desiredAccuracy = kCLLocationAccuracyNearestTenMeters
            manager.activityType = .other
            manager.distanceFilter = 20
            manager.pausesLocationUpdatesAutomatically = true
            manager.stopUpdatingLocation()
        }
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        Task { @MainActor in
            self.authorization = status
            if self.isAuthorized { self.manager.startUpdatingLocation() }
            if self.isDenied { self.location = nil }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let l = locations.last, l.horizontalAccuracy >= 0 else { return }
        let c = Coordinate(lat: l.coordinate.latitude, lon: l.coordinate.longitude), at = l.timestamp
        Task { @MainActor in
            self.location = c
            if self.isNavigating { self.onNavigationFix?(c, at) }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {}
}
