import Foundation

public enum Geo {
    /// Mean earth radius (IUGG), metres.
    public static let earthRadius = 6_371_008.8

    /// Great-circle distance in metres (haversine).
    public static func distance(_ a: Coordinate, _ b: Coordinate) -> Double {
        let p1 = a.lat * .pi / 180, p2 = b.lat * .pi / 180
        let dp = p2 - p1, dl = (b.lon - a.lon) * .pi / 180
        let h = sin(dp / 2) * sin(dp / 2) + cos(p1) * cos(p2) * sin(dl / 2) * sin(dl / 2)
        return 2 * earthRadius * asin(min(1, sqrt(h)))
    }

    /// The `limit` benches nearest to `origin`, nearest first; ties broken by id so the order is stable.
    public static func nearest(_ benches: [Bench], to origin: Coordinate, limit: Int = 50) -> [(bench: Bench, metres: Double)] {
        guard limit > 0 else { return [] }
        let scored = benches.map { (bench: $0, metres: distance(origin, $0.coordinate)) }
        return Array(scored.sorted { $0.metres != $1.metres ? $0.metres < $1.metres : $0.bench.id < $1.bench.id }.prefix(limit))
    }

    /// "80 m", "950 m", "1,2 km" (nl) / "1.2 km" (en), "12 km". Metres round to 10 under 1 km.
    public static func formatDistance(_ metres: Double, locale: Locale = .current) -> String {
        if metres < 1000 {
            let m = max(10, Int((metres / 10).rounded()) * 10)
            return m >= 1000 ? formatDistance(1000, locale: locale) : "\(m) m"
        }
        let km = metres / 1000
        let f = NumberFormatter()
        f.locale = locale
        f.numberStyle = .decimal
        f.maximumFractionDigits = km < 10 ? 1 : 0
        f.minimumFractionDigits = km < 10 ? 1 : 0
        return "\(f.string(from: NSNumber(value: km)) ?? String(format: "%.1f", km)) km"
    }
}
