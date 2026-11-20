import Foundation

/// The last good `/api/items?dataset=bench` body on disk (spec: "Offline / no network"). It lives in Caches,
/// so iOS may purge it; the map then just waits for the network. The file's modification date is the
/// "laatst bijgewerkt" time.
public struct ItemsCache: Sendable {
    public let file: URL

    public init(directory: URL) { file = directory.appending(path: "items-bench.json") }

    public static func standard() -> ItemsCache {
        ItemsCache(directory: FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0])
    }

    public func save(_ raw: Data, at date: Date = Date()) throws {
        try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        try raw.write(to: file, options: .atomic)
        try FileManager.default.setAttributes([.modificationDate: date], ofItemAtPath: file.path)
    }

    /// The cached benches and when they were fetched; nil when there is no usable cache.
    public func load() -> (benches: [Bench], fetchedAt: Date)? {
        guard let data = try? Data(contentsOf: file),
              let resp = try? ItemsResponse.decode(data), !resp.items.isEmpty,
              let date = (try? FileManager.default.attributesOfItem(atPath: file.path))?[.modificationDate] as? Date
        else { return nil }
        return (resp.items, date)
    }
}

/// What the map shows after a load.
public enum BenchLoad: Sendable {
    /// From the network just now.
    case fresh([Bench], fetchedAt: Date)
    /// The network failed; showing the last good copy (the "laatst bijgewerkt …" banner).
    case cached([Bench], fetchedAt: Date, error: APIError)
    /// The network failed and there is no cache (only the very first launch offline).
    case unavailable(APIError)

    public var benches: [Bench] {
        switch self {
        case .fresh(let b, _), .cached(let b, _, _): return b
        case .unavailable: return []
        }
    }
}

/// Network first, then the cache. A successful fetch with zero benches is not written over a good cache.
public struct BenchRepository: Sendable {
    public let client: APIClient
    public let cache: ItemsCache
    public init(client: APIClient, cache: ItemsCache) { self.client = client; self.cache = cache }

    public func cachedOnly() -> BenchLoad? {
        cache.load().map { .cached($0.benches, fetchedAt: $0.fetchedAt, error: .transport("not loaded yet")) }
    }

    public func load(now: Date = Date()) async -> BenchLoad {
        do {
            let (benches, raw) = try await client.items()
            if benches.isEmpty, let old = cache.load() {
                return .cached(old.benches, fetchedAt: old.fetchedAt, error: .decoding("empty response"))
            }
            try? cache.save(raw, at: now)
            return .fresh(benches, fetchedAt: now)
        } catch {
            let e = (error as? APIError) ?? .transport(error.localizedDescription)
            if let old = cache.load() { return .cached(old.benches, fetchedAt: old.fetchedAt, error: e) }
            return .unavailable(e)
        }
    }
}
