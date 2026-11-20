import Foundation

/// A point on the earth in WGS84 degrees. Foundation-only stand-in for CLLocationCoordinate2D.
public struct Coordinate: Hashable, Sendable, Codable {
    public var lat: Double
    public var lon: Double
    public init(lat: Double, lon: Double) { self.lat = lat; self.lon = lon }

    /// De Dam: the map's starting point, and the origin for "near me" when location is denied.
    public static let dam = Coordinate(lat: 52.3731, lon: 4.8926)
}
