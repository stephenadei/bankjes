import BankjesCore
import Foundation
import Observation

/// I5 sign-in state for the UI: the email step, "check your mail", the incoming link, the profile.
/// Token hygiene: nothing here logs a URL, a magic token or the session.
@MainActor @Observable
final class AuthModel {
    enum Step: Equatable {
        case enterEmail
        /// The link is on its way to this address.
        case checkMail(String)
    }

    struct Notice: Equatable {
        enum Kind { case error, info }
        let kind: Kind
        let text: String
        /// The server's own words (e.g. "invalid token"), shown small under the Dutch text.
        var detail: String? = nil
    }

    let environment: AppEnvironment
    let client: APIClient
    private let session: SessionManager

    private(set) var user: AuthUser?
    var isSignedIn: Bool { user != nil }
    private(set) var step: Step = .enterEmail
    var email = ""
    private(set) var busy = false
    private(set) var exchanging = false
    var notice: Notice?
    /// The account sheet; opened by an incoming link and by a 401.
    var showAccount = false
    private(set) var lastSent: Date?
    static let resendCooldown: TimeInterval = 30
    /// Debug `-BankjesAccount profile`: keep the fake session on screen (no `/api/me`).
    private var debugNoRefresh = false

    init(environment: AppEnvironment, client: APIClient, session: SessionManager) {
        self.environment = environment; self.client = client; self.session = session
        user = session.user
        session.onChange = { [weak self] change in
            Task { @MainActor in self?.apply(change) }
        }
    }

    private func apply(_ change: SessionManager.Change) {
        switch change {
        case .signedIn(let u):
            user = u
        case .signedOut:
            user = nil
        case .expired:
            guard user != nil else { return }
            user = nil
            step = .enterEmail
            notice = Notice(kind: .info, text: String(localized: "Je sessie is verlopen. Log opnieuw in."))
            showAccount = true
        }
    }

    /// On launch and on return to the foreground: check the stored session (a 401 signs out via the client).
    func refresh() async {
        guard session.isSignedIn, !debugNoRefresh else { return }
        if let u = try? await client.me() { user = u }
    }

    // MARK: email → link

    func sendLink() async {
        guard let address = EmailAddress.normalise(email) else {
            notice = Notice(kind: .error, text: String(localized: "Vul een geldig e-mailadres in."))
            return
        }
        busy = true; notice = nil
        defer { busy = false }
        do {
            try await client.requestMagicLink(email: address)
            email = address
            lastSent = Date()
            step = .checkMail(address)
        } catch {
            notice = Self.notice(for: error, sending: true)
        }
    }

    func canResend(at now: Date) -> Bool {
        guard let lastSent else { return true }
        return now.timeIntervalSince(lastSent) >= Self.resendCooldown
    }

    func resend() async {
        guard case .checkMail(let address) = step else { return }
        email = address
        await sendLink()
        if notice == nil {
            notice = Notice(kind: .info, text: String(localized: "We hebben een nieuwe link gestuurd."))
        }
    }

    func changeEmail() {
        step = .enterEmail
        notice = nil
    }

    // MARK: the link

    /// `.onOpenURL` / a Universal Link activity. Only `https://<this env>/auth/app?token=…` is exchanged.
    func handle(url: URL) async {
        switch MagicLink.parse(url, for: environment) {
        case .rejected:
            return   // not a sign-in link (and nothing else in the app is linkable yet)
        case .wrongEnvironment(let link, let app):
            showAccount = true
            notice = Notice(kind: .error, text: Self.mismatchText(link: link, app: app))
        case .token(let token):
            showAccount = true
            exchanging = true; notice = nil
            defer { exchanging = false }
            do {
                user = try await client.signIn(withMagicToken: token)
                step = .enterEmail
                email = ""
            } catch {
                notice = Self.notice(for: error, sending: false)
            }
        }
    }

    func signOut() {
        session.signOut()
        user = nil
        step = .enterEmail
        email = ""
        notice = nil
    }

    #if DEBUG
    /// Debug only, for repeatable simulator screenshots without sending mail:
    /// `-BankjesAccount open` opens the sheet, `-BankjesAccount checkmail` shows "check your mail" for a
    /// placeholder address (no request is sent), `-BankjesOpenURL <url>` feeds a URL through `handle(url:)`
    /// exactly as `.onOpenURL` would (e.g. a prd link, to see the env-mismatch message).
    /// `-BankjesAccount profile` stores a fake session and shows the profile (no server call);
    /// `-BankjesAccount expired` stores a fake session and lets the launch `/api/me` get the server's real 401.
    /// Returns false when the launch refresh must be skipped.
    func applyDebugLaunchArguments() async -> Bool {
        let d = UserDefaults.standard
        let fake = StoredSession(session: "debug-not-a-session",
                                 user: AuthUser(id: "debug", email: "naam@voorbeeld.nl", displayName: "naam", isAdmin: false))
        switch d.string(forKey: "BankjesAccount") {
        case "open": showAccount = true
        case "checkmail": step = .checkMail("naam@voorbeeld.nl"); lastSent = Date(); showAccount = true
        case "profile": try? session.signIn(fake); user = fake.user; showAccount = true; debugNoRefresh = true; return false
        case "expired": try? session.signIn(fake); user = fake.user
        default: break
        }
        if let s = d.string(forKey: "BankjesOpenURL"), let url = URL(string: s) { await handle(url: url) }
        return true
    }
    #endif

    // MARK: Dutch messages

    static func mismatchText(link: AppEnvironment, app: AppEnvironment) -> String {
        func name(_ e: AppEnvironment) -> String {
            switch e {
            case .prd: return String(localized: "de gewone Bankjes-app")
            case .acc: return String(localized: "de testversie (acc)")
            default: return e.apiBase.host ?? e.label
            }
        }
        let l = name(link), a = name(app)
        return String(localized: "Deze inloglink is voor \(l), maar je opende hem in \(a). Je bent niet ingelogd. Vraag een nieuwe link aan in deze app.")
    }

    static func notice(for error: Error, sending: Bool) -> Notice {
        guard let api = error as? APIError else {
            return Notice(kind: .error, text: String(localized: "Er ging iets mis. Probeer het opnieuw."))
        }
        switch api {
        case .transport:
            return Notice(kind: .error, text: String(localized: "Geen verbinding. Controleer je internet en probeer het opnieuw."))
        case .decoding:
            return Notice(kind: .error, text: String(localized: "Onverwacht antwoord van de server. Probeer het later opnieuw."))
        case .http(let status, let detail):
            let text: String
            switch (sending, status, detail) {
            case (true, 400, _): text = String(localized: "Dit e-mailadres wordt niet geaccepteerd.")
            case (true, _, _): text = String(localized: "De inlogmail kon niet worden verstuurd. Probeer het later opnieuw.")
            case (false, 410, "link already used"?): text = String(localized: "Deze inloglink is al gebruikt. Vraag een nieuwe link aan.")
            case (false, 410, _): text = String(localized: "Deze inloglink is verlopen. Vraag een nieuwe link aan.")
            case (false, 400, _): text = String(localized: "Deze inloglink is ongeldig. Vraag een nieuwe link aan.")
            case (false, _, _): text = String(localized: "Inloggen is mislukt. Probeer het later opnieuw.")
            }
            return Notice(kind: .error, text: text, detail: detail.map { "\(status) \($0)" } ?? "\(status)")
        }
    }
}
