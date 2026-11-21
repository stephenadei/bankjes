import Foundation
#if canImport(Security)
import Security
#endif

// I5 sign-in (spec docs/specs/2026-11-20-ios-app.md, "Auth design"): magic link with client "ios" → the
// Universal Link https://<env host>/auth/app?token=… opens the app → POST /api/auth/token → Bearer session,
// kept in the Keychain. Token hygiene: neither the magic token nor the session is ever printed; every type
// that holds one redacts it in its description.

/// `user` from `/api/auth/token` and `/api/me`.
public struct AuthUser: Codable, Equatable, Sendable {
    public let id: String
    public let email: String
    public let displayName: String
    public let isAdmin: Bool

    public init(id: String, email: String, displayName: String, isAdmin: Bool) {
        self.id = id; self.email = email; self.displayName = displayName; self.isAdmin = isAdmin
    }

    enum CodingKeys: String, CodingKey {
        case id, email, displayName = "display_name", isAdmin = "is_admin"
    }
}

/// What the Keychain holds: the Bearer session plus the user it belongs to (for the profile on relaunch).
public struct StoredSession: Codable, Equatable, Sendable, CustomStringConvertible, CustomDebugStringConvertible {
    public let session: String
    public let user: AuthUser
    public init(session: String, user: AuthUser) { self.session = session; self.user = user }
    public var description: String { "StoredSession(user: \(user.id), session: <redacted>)" }
    public var debugDescription: String { description }
}

// MARK: - The magic link

/// What a URL handed to the app (`.onOpenURL` / a Universal Link activity) turns out to be.
public enum MagicLink: Equatable, Sendable, CustomStringConvertible {
    /// A sign-in link for this build's backend.
    case token(String)
    /// A sign-in link for the other backend (prd link in an acc build or vice versa): never exchanged.
    case wrongEnvironment(link: AppEnvironment, app: AppEnvironment)
    /// Not ours: another host, another path, not https, or no token.
    case rejected

    public var description: String {
        switch self {
        case .token: return "MagicLink.token(<redacted>)"
        case .wrongEnvironment(let link, let app): return "MagicLink.wrongEnvironment(link: \(link.label), app: \(app.label))"
        case .rejected: return "MagicLink.rejected"
        }
    }

    /// The backends a sign-in link can come from. Only these hosts are claimed in the entitlements.
    public static let knownEnvironments: [AppEnvironment] = [.acc, .prd]

    /// Parses `https://<host>/auth/app?token=…`. The host must be this build's backend; a link from the other
    /// known backend is `.wrongEnvironment`, anything else `.rejected`. `/auth/verify` (the web login) is
    /// rejected too: the app only claims `/auth/app`.
    public static func parse(_ url: URL, for env: AppEnvironment) -> MagicLink {
        guard let comps = URLComponents(url: url, resolvingAgainstBaseURL: false),
              comps.scheme?.lowercased() == "https",
              comps.user == nil, comps.password == nil,
              comps.port == nil || comps.port == 443,
              let host = comps.host?.lowercased(), !host.isEmpty,
              comps.path == "/auth/app" || comps.path == "/auth/app/"
        else { return .rejected }
        let tokens = (comps.queryItems ?? []).filter { $0.name == "token" }
        guard tokens.count == 1, let token = tokens[0].value, !token.isEmpty, token.count <= 4096 else { return .rejected }

        if host == env.apiBase.host?.lowercased() { return .token(token) }
        if let other = knownEnvironments.first(where: { $0.apiBase.host?.lowercased() == host }) {
            return .wrongEnvironment(link: other, app: env)
        }
        return .rejected
    }
}

/// The same rule as the backend's `_EMAIL_RE` (`^[^@\s]+@[^@\s]+\.[^@\s]+$`), after trim + lowercase.
public enum EmailAddress {
    public static func normalise(_ raw: String) -> String? {
        let e = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let parts = e.split(separator: "@", omittingEmptySubsequences: false)
        guard parts.count == 2, !parts[0].isEmpty, !e.contains(where: \.isWhitespace) else { return nil }
        let domain = parts[1]
        guard let dot = domain.lastIndex(of: "."), dot != domain.startIndex, domain.index(after: dot) != domain.endIndex
        else { return nil }
        return e
    }
}

// MARK: - Storage

/// Where the session lives. The app uses `KeychainSessionStore`; the checks use `MemorySessionStore`.
public protocol SessionStore: Sendable {
    func load() -> StoredSession?
    func save(_ session: StoredSession) throws
    func clear()
}

public final class MemorySessionStore: SessionStore, @unchecked Sendable {
    private let lock = NSLock()
    private var value: StoredSession?
    public init(_ value: StoredSession? = nil) { self.value = value }
    public func load() -> StoredSession? { lock.withLock { value } }
    public func save(_ session: StoredSession) throws { lock.withLock { value = session } }
    public func clear() { lock.withLock { value = nil } }
}

#if canImport(Security)
/// One generic-password item, `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`: readable by background
/// work after the first unlock, never in a backup or on another device.
public struct KeychainSessionStore: SessionStore {
    public let service: String
    public let account: String
    public init(service: String = "app.stephensprive.bankjes.session", account: String) {
        self.service = service; self.account = account
    }

    private var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: account]
    }

    public func load() -> StoredSession? {
        var q = query
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let data = out as? Data else { return nil }
        return try? JSONDecoder().decode(StoredSession.self, from: data)
    }

    public func save(_ session: StoredSession) throws {
        let data = try JSONEncoder().encode(session)
        SecItemDelete(query as CFDictionary)
        var add = query
        add[kSecValueData as String] = data
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(add as CFDictionary, nil)
        guard status == errSecSuccess else { throw APIError.transport("keychain status \(status)") }
    }

    public func clear() { SecItemDelete(query as CFDictionary) }
}
#endif

// MARK: - The session

/// The signed-in state, shared by the APIClient (Bearer on every request, a 401 signs out) and the UI.
/// Thread-safe; `onChange` fires on every transition (the app hops to the main actor itself).
public final class SessionManager: @unchecked Sendable, CustomStringConvertible {
    public enum Change: Equatable, Sendable {
        case signedIn(AuthUser)
        case signedOut
        /// The server answered 401 to our Bearer: the session is gone, the user must sign in again.
        case expired
    }

    private let store: SessionStore
    private let lock = NSLock()
    private var current: StoredSession?
    public var onChange: (@Sendable (Change) -> Void)?

    public init(store: SessionStore) {
        self.store = store
        current = store.load()
    }

    public var user: AuthUser? { lock.withLock { current?.user } }
    public var isSignedIn: Bool { lock.withLock { current != nil } }
    /// The Bearer value; only APIClient reads it.
    var bearer: String? { lock.withLock { current?.session } }

    public func signIn(_ session: StoredSession) throws {
        try store.save(session)
        lock.withLock { current = session }
        onChange?(.signedIn(session.user))
    }

    /// `/api/me` returned a (possibly renamed) user for the same session.
    public func update(user: AuthUser) {
        let updated: StoredSession? = lock.withLock {
            guard let c = current, c.user != user else { return nil }
            current = StoredSession(session: c.session, user: user)
            return current
        }
        if let updated { try? store.save(updated) }
    }

    public func signOut() {
        store.clear()
        lock.withLock { current = nil }
        onChange?(.signedOut)
    }

    /// A 401 to `sentBearer`. Ignored if the session changed meanwhile (a sign-in raced the request).
    func invalidate(sentBearer: String) {
        let cleared: Bool = lock.withLock {
            guard current?.session == sentBearer else { return false }
            current = nil
            return true
        }
        guard cleared else { return }
        store.clear()
        onChange?(.expired)
    }

    public var description: String { "SessionManager(signedIn: \(isSignedIn))" }
}

// MARK: - Auth endpoints

/// `POST /api/auth/token` → `{session, user}`.
public struct TokenExchangeResponse: Decodable, Sendable, CustomStringConvertible {
    public let session: String
    public let user: AuthUser
    public var description: String { "TokenExchangeResponse(user: \(user.id), session: <redacted>)" }
}

extension APIClient {
    public func magicLinkRequest(email: String) -> URLRequest {
        jsonPost("api/auth/request-magic-link", body: ["email": email, "client": "ios"])
    }

    /// `POST /api/auth/request-magic-link {email, client:"ios"}`: the mail's link is `/auth/app?token=…`.
    public func requestMagicLink(email: String) async throws {
        _ = try await get(magicLinkRequest(email: email))
    }

    public func tokenExchangeRequest(token: String) -> URLRequest {
        jsonPost("api/auth/token", body: ["token": token])
    }

    /// `POST /api/auth/token {token}`. Does not store anything; `signIn(withMagicToken:)` does.
    public func exchangeToken(_ token: String) async throws -> TokenExchangeResponse {
        let data = try await get(tokenExchangeRequest(token: token))
        do { return try JSONDecoder().decode(TokenExchangeResponse.self, from: data) } catch {
            throw APIError.decoding("token exchange response")   // never echo the body: it holds the session
        }
    }

    /// Exchange + store in the session (Keychain). Returns the user.
    @discardableResult
    public func signIn(withMagicToken token: String) async throws -> AuthUser {
        guard let session else { throw APIError.transport("no session store") }
        let r = try await exchangeToken(token)
        try session.signIn(StoredSession(session: r.session, user: r.user))
        return r.user
    }

    public func meRequest() -> URLRequest {
        var req = URLRequest(url: environment.apiBase.appending(path: "api/me"))
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        return req
    }

    /// `GET /api/me` with the Bearer; refreshes the stored user. A 401 signs out (in `get`).
    @discardableResult
    public func me() async throws -> AuthUser {
        let data = try await get(meRequest())
        guard let user = try? JSONDecoder().decode(AuthUser.self, from: data) else { throw APIError.decoding("me") }
        session?.update(user: user)
        return user
    }

    func jsonPost(_ path: String, body: [String: String]) -> URLRequest {
        var req = URLRequest(url: environment.apiBase.appending(path: path))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.httpBody = try? JSONSerialization.data(withJSONObject: body, options: [.sortedKeys])
        return req
    }
}
