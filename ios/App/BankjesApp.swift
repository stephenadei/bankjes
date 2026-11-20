import BankjesCore
import SwiftUI

@main
struct BankjesApp: App {
    @State private var model = AppModel(environment: AppConfig.environment)
    @State private var location = LocationProvider()

    var body: some Scene {
        WindowGroup {
            MapScreen()
                .environment(model)
                .environment(location)
        }
    }
}
