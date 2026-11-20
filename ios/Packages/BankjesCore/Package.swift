// swift-tools-version:5.10
// BankjesCore: everything in the iPhone app that is not UI: the bench model, the API client, the on-disk
// items cache and the distance sort. Foundation only, so it builds and is checked on the Mac with the
// Command Line Tools alone: `swift run BankjesChecks ../../Fixtures` (exit 0 = all passed; no XCTest).
import PackageDescription

let package = Package(
    name: "BankjesCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "BankjesCore", targets: ["BankjesCore"])],
    targets: [
        .target(name: "BankjesCore"),
        .executableTarget(name: "BankjesChecks", dependencies: ["BankjesCore"]),
    ]
)
