import BankjesCore
import Foundation
import Observation

@MainActor @Observable
final class AppModel {
    enum Status: Equatable {
        case loading
        case fresh(Date)
        /// Network failed; the map shows the last good copy from this date.
        case stale(Date)
        /// Network failed and nothing is cached (only the very first launch offline).
        case unavailable
    }

    let environment: AppEnvironment
    private let repository: BenchRepository

    private(set) var benches: [Bench] = []
    private(set) var status: Status = .loading
    /// Bumped on every new bench list, so the map only diffs its annotations when the data really changed.
    private(set) var benchesVersion = 0
    /// A request to centre the map on a bench (I3 "tap to centre"); the map clears it once applied.
    var focus: Bench?

    init(environment: AppEnvironment, client: APIClient? = nil, repository: BenchRepository? = nil) {
        self.environment = environment
        self.repository = repository
            ?? BenchRepository(client: client ?? APIClient(environment: environment), cache: .standard())
        if let cached = self.repository.cachedOnly() { apply(cached, initial: true) }
    }

    func load() async {
        if benches.isEmpty { status = .loading }
        apply(await repository.load(), initial: false)
    }

    private func apply(_ load: BenchLoad, initial: Bool) {
        switch load {
        case .fresh(let b, let at):
            set(b); status = .fresh(at)
        case .cached(let b, let at, _):
            set(b)
            // The first frame shows the cache while the network loads: not "offline" yet.
            status = initial ? .loading : .stale(at)
        case .unavailable:
            status = benches.isEmpty ? .unavailable : status
        }
    }

    private func set(_ b: [Bench]) {
        guard b.map(\.id) != benches.map(\.id) else { return }
        benches = b
        benchesVersion += 1
    }
}
