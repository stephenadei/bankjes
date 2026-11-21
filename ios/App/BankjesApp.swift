import BankjesCore
import SwiftUI

@main
struct BankjesApp: App {
    @State private var model = AppModel(environment: AppConfig.environment)
    @State private var location: LocationProvider
    @State private var nav: NavigationModel

    init() {
        let location = LocationProvider()
        _location = State(initialValue: location)
        _nav = State(initialValue: NavigationModel(client: APIClient(environment: AppConfig.environment), location: location))
    }

    var body: some Scene {
        WindowGroup {
            MapScreen()
                .environment(model)
                .environment(location)
                .environment(nav)
        }
    }
}
