import Foundation

/// Which backend a build talks to. The value comes from Info.plist `BankjesAPIBase`, which project.yml fills
/// per configuration: Debug → acc, Release (TestFlight) → prd (spec decision D1).
public struct AppEnvironment: Equatable, Sendable {
    public let apiBase: URL

    public static let acc = AppEnvironment(apiBase: URL(string: "https://bankjes-acc.stephensprive.app")!)
    public static let prd = AppEnvironment(apiBase: URL(string: "https://bankjes.stephenadei.nl")!)

    public init(apiBase: URL) { self.apiBase = apiBase }

    /// Parses the Info.plist value. Only an https URL with a host is accepted; a trailing slash is dropped.
    public init?(infoValue: Any?) {
        guard var s = (infoValue as? String)?.trimmingCharacters(in: .whitespaces), !s.isEmpty else { return nil }
        while s.hasSuffix("/") { s.removeLast() }
        guard let url = URL(string: s), url.scheme == "https", let host = url.host, !host.isEmpty else { return nil }
        self.apiBase = url
    }

    /// Short label for the UI ("acc" / "prd" / host).
    public var label: String {
        switch apiBase.host {
        case AppEnvironment.prd.apiBase.host: return "prd"
        case AppEnvironment.acc.apiBase.host: return "acc"
        default: return apiBase.host ?? "?"
        }
    }
}
