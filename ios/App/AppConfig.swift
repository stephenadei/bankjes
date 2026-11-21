import BankjesCore
import Foundation
import MapKit

enum AppConfig {
    /// Info.plist `BankjesAPIBase` (project.yml: Debug → acc, Release → prd). A broken value falls back to
    /// acc in Debug and prd in Release, so a misconfigured build never silently points a TestFlight user at acc.
    static let environment: AppEnvironment = {
        #if DEBUG
        // Debug only: `-BankjesAPIBase https://…` overrides the base (e.g. an unreachable host to see the
        // offline banner in the simulator, which shares the Mac's network and has no airplane mode).
        if let env = AppEnvironment(infoValue: UserDefaults.standard.string(forKey: "BankjesAPIBase")) { return env }
        #endif
        if let env = AppEnvironment(infoValue: Bundle.main.object(forInfoDictionaryKey: "BankjesAPIBase")) { return env }
        #if DEBUG
        return .acc
        #else
        return .prd
        #endif
    }()

    /// Debug only: `-BankjesRegion lat,lon,metres` as a launch argument starts the map there (repeatable
    /// simulator screenshots). Release builds always start on Amsterdam.
    static let startRegion: MKCoordinateRegion? = {
        #if DEBUG
        guard let v = UserDefaults.standard.string(forKey: "BankjesRegion") else { return nil }
        let p = v.split(separator: ",").compactMap { Double($0.trimmingCharacters(in: .whitespaces)) }
        guard p.count == 3 else { return nil }
        return MKCoordinateRegion(center: CLLocationCoordinate2D(latitude: p[0], longitude: p[1]),
                                  latitudinalMeters: p[2], longitudinalMeters: p[2])
        #else
        return nil
        #endif
    }()

    /// Debug only: `-BankjesNavTo <bench id | lat,lon>` opens the route preview to that bench once the benches have
    /// loaded (simulator runs of I4; `-bj-nav-mode bike|wheelchair` picks the mode).
    static let debugNavTo: String? = {
        #if DEBUG
        return UserDefaults.standard.string(forKey: "BankjesNavTo")
        #else
        return nil
        #endif
    }()
}
