import BankjesCore
import CoreLocation
import Observation

/// When-In-Use location for "near me". Never asks for "Always".
@MainActor @Observable
final class LocationProvider: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private(set) var authorization: CLAuthorizationStatus
    private(set) var location: Coordinate?

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

    func stop() { manager.stopUpdatingLocation() }

    // I4 hook (decision D2): navigation turns on `allowsBackgroundLocationUpdates` here, only while navigating,
    // with `UIBackgroundModes: [location]` in project.yml and best accuracy / `.fitness`. Not used before I4.
    func setNavigating(_ on: Bool) {}

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
        let c = Coordinate(lat: l.coordinate.latitude, lon: l.coordinate.longitude)
        Task { @MainActor in self.location = c }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {}
}
