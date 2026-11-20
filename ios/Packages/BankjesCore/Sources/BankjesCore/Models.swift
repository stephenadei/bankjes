import Foundation

/// One bench Marker from `GET /api/items?dataset=bench` (CONTEXT.md: Marker). `props` upstream is raw
/// (a full BGT record, or OSM tags plus `source_type`); the app keeps only what it shows.
public struct Bench: Identifiable, Hashable, Sendable {
    public enum Source: String, Sendable { case bgt, osm, other }

    public let id: String
    public let coordinate: Coordinate
    public let source: Source
    /// OSM `backrest` tag: true = "yes", false = "no", nil = unknown (and always nil for BGT).
    public let backrest: Bool?

    public init(id: String, coordinate: Coordinate, source: Source, backrest: Bool?) {
        self.id = id; self.coordinate = coordinate; self.source = source; self.backrest = backrest
    }
}

extension Bench: Decodable {
    private enum Keys: String, CodingKey { case id, lat, lon, props }
    private enum PropKeys: String, CodingKey { case source_type, backrest }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        let id = try c.decode(String.self, forKey: .id)
        let lat = try c.decode(Double.self, forKey: .lat), lon = try c.decode(Double.self, forKey: .lon)
        guard !id.isEmpty, (-90...90).contains(lat), (-180...180).contains(lon) else {
            throw DecodingError.dataCorruptedError(forKey: .id, in: c, debugDescription: "bad id or coordinate")
        }
        var source = Source.other, backrest: Bool?
        if let p = try? c.nestedContainer(keyedBy: PropKeys.self, forKey: .props) {
            source = (try? p.decodeIfPresent(String.self, forKey: .source_type)).flatMap { $0 }.flatMap(Source.init(rawValue:)) ?? .other
            switch (try? p.decodeIfPresent(String.self, forKey: .backrest)).flatMap({ $0 })?.lowercased() {
            case "yes": backrest = true
            case "no": backrest = false
            default: backrest = nil
            }
        }
        self.init(id: id, coordinate: Coordinate(lat: lat, lon: lon), source: source, backrest: backrest)
    }
}

/// `{count, items:[…]}`. An item that does not decode is dropped; the rest stays (one bad upstream row must
/// not blank the map).
public struct ItemsResponse: Decodable, Sendable {
    public let count: Int
    public let items: [Bench]

    private struct Lenient: Decodable {
        let bench: Bench?
        init(from decoder: Decoder) throws { bench = try? Bench(from: decoder) }
    }
    private enum Keys: String, CodingKey { case count, items }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        items = try c.decode([Lenient].self, forKey: .items).compactMap(\.bench)
        count = (try? c.decode(Int.self, forKey: .count)) ?? items.count
    }

    public static func decode(_ data: Data) throws -> ItemsResponse {
        try JSONDecoder().decode(ItemsResponse.self, from: data)
    }
}
