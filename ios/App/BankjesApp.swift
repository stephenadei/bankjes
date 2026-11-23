import BankjesCore
import SwiftUI

@main
struct BankjesApp: App {
    @State private var model: AppModel
    @State private var auth: AuthModel
    @State private var location: LocationProvider
    @State private var nav: NavigationModel
    @Environment(\.scenePhase) private var scenePhase

    init() {
        let env = AppConfig.environment
        // I5: one session (Keychain, per backend host) and one client, so every request carries the Bearer.
        let session = SessionManager(store: KeychainSessionStore(account: env.apiBase.host ?? "bankjes"))
        let client = APIClient(environment: env, session: session)
        _model = State(initialValue: AppModel(environment: env, client: client))
        _auth = State(initialValue: AuthModel(environment: env, client: client, session: session))
        // I4: navigation shares the signed-in client and the one LocationProvider.
        let location = LocationProvider()
        _location = State(initialValue: location)
        _nav = State(initialValue: NavigationModel(client: client, location: location))
    }

    var body: some Scene {
        WindowGroup {
            MapScreen()
                .overlay(alignment: .bottomLeading) { AccountButton() }
                .sheet(isPresented: $auth.showAccount) { AccountScreen() }
                .environment(model)
                .environment(auth)
                .environment(location)
                .environment(nav)
                // The magic link: https://<env host>/auth/app?token=… (Universal Link). Never logged.
                .onOpenURL { url in Task { await auth.handle(url: url) } }
                .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in
                    guard let url = activity.webpageURL else { return }
                    Task { await auth.handle(url: url) }
                }
                .task {
                    #if DEBUG
                    guard await auth.applyDebugLaunchArguments() else { return }
                    #endif
                    await auth.refresh()
                }
                .onChange(of: scenePhase) { _, phase in
                    if phase == .active { Task { await auth.refresh() } }
                }
        }
    }
}
