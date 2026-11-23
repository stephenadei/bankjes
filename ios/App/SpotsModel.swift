import BankjesCore
import Foundation
import Observation

/// I6 Spots (Plekjes) for the UI: the visible list, the sheets, and the writes. Writes are online only: one
/// request, on failure a Dutch error and the list unchanged; nothing is queued or retried in the background.
@MainActor @Observable
final class SpotsModel {
    /// The one Spots sheet on the map (a single `.sheet(item:)` avoids stacked sheet conflicts).
    enum Sheet: Identifiable, Equatable {
        case list
        case add(Coordinate)
        case detail(String)
        var id: String {
            switch self {
            case .list: return "list"
            case .add(let c): return "add-\(c.lat),\(c.lon)"
            case .detail(let id): return "detail-\(id)"
            }
        }
    }

    private let client: APIClient
    /// All Spots this user may see (own + public approved), newest first, as the server orders them.
    private(set) var spots: [Spot] = []
    private(set) var version = 0
    private(set) var loadFailed = false
    var sheet: Sheet?
    /// The last centre the map reported, for "add at the map centre". Not observed: it changes on every pan.
    @ObservationIgnored var mapCentre: Coordinate = .dam
    /// Set by the map screen: what to do after a 401 (the session is gone; show sign-in).
    @ObservationIgnored var onSignedOut: (() -> Void)?

    init(client: APIClient) { self.client = client }

    var userId: String? { client.session?.user?.id }
    var isSignedIn: Bool { client.session?.isSignedIn == true }
    var own: [Spot] { SpotFilter.own(spots, userId: userId) }
    func spot(_ id: String) -> Spot? { spots.first { $0.id == id } }
    func isOwn(_ spot: Spot) -> Bool { spot.isOwned(by: userId) }

    func load() async {
        do {
            set(try await client.spots())
            loadFailed = false
        } catch {
            // Keep what is shown; signed-out users simply see no own Spots.
            loadFailed = true
            if !isSignedIn { set(SpotFilter.visible(spots, to: nil)) }
        }
    }

    /// Sign-out: drop own Spots immediately, before the reload.
    func signedOut() { set(SpotFilter.visible(spots, to: nil)) }

    private func set(_ s: [Spot]) {
        guard s != spots else { return }
        spots = s
        version += 1
    }

    private func replace(_ s: Spot) {
        var all = spots
        if let i = all.firstIndex(where: { $0.id == s.id }) { all[i] = s } else { all.insert(s, at: 0) }
        set(SpotFilter.visible(all, to: userId))
    }

    // MARK: writes (each returns an error text, nil on success)

    func create(_ draft: SpotDraft, at c: Coordinate) async -> String? {
        await write { replace(try await client.createSpot(draft, at: c)) }
    }

    func update(_ spot: Spot, with draft: SpotDraft) async -> String? {
        await write { replace(try await client.updateSpot(spot, with: draft)) }
    }

    func delete(_ spot: Spot) async -> String? {
        await write {
            try await client.deleteSpot(id: spot.id)
            set(spots.filter { $0.id != spot.id })
        }
    }

    func requestPublic(_ spot: Spot) async -> String? {
        await write { replace(try await client.requestPublic(id: spot.id)) }
    }

    func revokePublic(_ spot: Spot) async -> String? {
        await write { replace(try await client.revokePublic(id: spot.id)) }
    }

    private func write(_ body: () async throws -> Void) async -> String? {
        guard isSignedIn else { return String(localized: "Log in om je plekjes te bewaren.") }
        do {
            try await body()
            return nil
        } catch {
            if (error as? APIError)?.isUnauthorized == true {
                signedOut()
                sheet = nil
                onSignedOut?()
            }
            return Self.errorText(error)
        }
    }

    static func errorText(_ error: Error) -> String {
        guard let api = error as? APIError else { return String(localized: "Er ging iets mis. Probeer het opnieuw.") }
        switch api {
        case .transport:
            return String(localized: "Geen verbinding. Je wijziging is niet opgeslagen; probeer het opnieuw als je online bent.")
        case .decoding:
            return String(localized: "Onverwacht antwoord van de server. Probeer het later opnieuw.")
        case .http(let status, _):
            switch status {
            case 401: return String(localized: "Je sessie is verlopen. Log opnieuw in.")
            case 403: return String(localized: "Dit plekje is niet van jou.")
            case 404: return String(localized: "Dit plekje bestaat niet meer.")
            case 409: return String(localized: "Dit plekje is al openbaar.")
            case 400, 422: return String(localized: "Controleer de naam, beschrijving en soort.")
            default: return String(localized: "De server kon je wijziging niet opslaan (\(status)). Probeer het later opnieuw.")
            }
        }
    }
}

/// Dutch names for categories and statuses.
enum SpotText {
    static func category(_ c: SpotCategory?) -> String {
        switch c ?? .anders {
        case .bank: return String(localized: "Bank")
        case .stoel: return String(localized: "Stoel")
        case .picknicktafel: return String(localized: "Picknicktafel")
        case .krukje: return String(localized: "Krukje")
        case .anders: return String(localized: "Anders")
        }
    }

    static func categoryIcon(_ c: SpotCategory?) -> String {
        switch c ?? .anders {
        case .bank: return "chair.lounge.fill"
        case .stoel: return "chair.fill"
        case .picknicktafel: return "table.furniture.fill"
        case .krukje: return "circle.fill"
        case .anders: return "star.fill"
        }
    }

    static func status(_ s: SpotPublicStatus) -> String {
        switch s {
        case .none: return String(localized: "Privé")
        case .requested: return String(localized: "Openbaar aangevraagd")
        case .approved: return String(localized: "Openbaar")
        case .denied: return String(localized: "Afgewezen")
        case .revoked: return String(localized: "Ingetrokken")
        case .unknown: return String(localized: "Onbekend")
        }
    }

    static func statusExplanation(_ s: SpotPublicStatus) -> String {
        switch s {
        case .none: return String(localized: "Alleen jij ziet dit plekje.")
        case .requested: return String(localized: "Je aanvraag wacht op goedkeuring. Tot dan ziet alleen jij dit plekje.")
        case .approved: return String(localized: "Iedereen ziet dit plekje op de kaart.")
        case .denied: return String(localized: "Je aanvraag is afgewezen. Alleen jij ziet dit plekje; je kunt het opnieuw aanvragen.")
        case .revoked: return String(localized: "Je hebt openbaar ingetrokken. Alleen jij ziet dit plekje.")
        case .unknown: return String(localized: "De status is onbekend in deze versie van de app.")
        }
    }

    static func statusIcon(_ s: SpotPublicStatus) -> String {
        switch s {
        case .none: return "lock.fill"
        case .requested: return "hourglass"
        case .approved: return "globe.europe.africa.fill"
        case .denied: return "xmark.octagon.fill"
        case .revoked: return "arrow.uturn.backward.circle.fill"
        case .unknown: return "questionmark.circle"
        }
    }
}
