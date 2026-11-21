import BankjesCore
import MapKit
import SwiftUI

/// Amsterdam at city zoom, centred on the Dam.
let amsterdamRegion = MKCoordinateRegion(
    center: CLLocationCoordinate2D(latitude: Coordinate.dam.lat, longitude: Coordinate.dam.lon),
    span: MKCoordinateSpan(latitudeDelta: 0.12, longitudeDelta: 0.12))

struct MapScreen: View {
    @Environment(AppModel.self) private var model
    @Environment(NavigationModel.self) private var nav
    @Environment(\.scenePhase) private var scenePhase
    @State private var showNearMe = false
    @State private var debugNavDone = false

    var body: some View {
        // Reading model.focus here (not a binding) is what makes the view update when the list sets it.
        ClusterMapView(benches: model.benches, version: model.benchesVersion, focus: model.focus,
                       focusHandled: { model.focus = nil },
                       route: nav.route?.geometry, routeVersion: nav.routeVersion,
                       navigating: nav.phase == .navigating, fixCount: nav.fixCount,
                       onRoute: { nav.preview($0) })
            .ignoresSafeArea()
            .overlay(alignment: .top) {
                VStack(spacing: 6) {
                    EnvBadge(environment: model.environment)
                    if nav.phase != .navigating {
                        StatusBanner(status: model.status, retry: { Task { await model.load() } })
                    }
                }
            }
            .overlay {
                if nav.phase == .navigating { NavLiveOverlay().padding(.top, 22) }
            }
            .overlay(alignment: .bottom) {
                if nav.phase == .arrived { NavArrivedCard() }
            }
            .overlay(alignment: .bottom) {
                if !nav.isActive { nearMeButton }
            }
            .sheet(isPresented: $showNearMe, onDismiss: { nav.openQueued() }) {
                NearMeList().presentationDetents([.medium, .large])
            }
            .sheet(isPresented: Binding(get: { nav.showsSheet }, set: { if !$0 && nav.showsSheet { nav.stop() } })) {
                NavPreviewSheet()
                    .presentationDetents([.height(340), .large])
                    .presentationBackgroundInteraction(.enabled(upThrough: .height(340)))
            }
            .task { await model.load() }
            .onChange(of: model.benchesVersion) { _, _ in openDebugRoute() }
            .onAppear { openDebugRoute() }
            .onChange(of: scenePhase) { _, phase in
                // Back from the background with a stale map: try again.
                if phase == .active, case .stale = model.status { Task { await model.load() } }
            }
    }

    private var nearMeButton: some View {
                Button { showNearMe = true } label: {
                    Label("In de buurt", systemImage: "list.bullet.below.rectangle")
                        .font(.headline)
                        .padding(.horizontal, 20).padding(.vertical, 12)
                }
                .buttonStyle(.borderedProminent)
                .buttonBorderShape(.capsule)
                .shadow(radius: 4, y: 2)
                .padding(.bottom, 12)
                .disabled(model.benches.isEmpty)
    }

    private func openDebugRoute() {
        guard !debugNavDone, let id = AppConfig.debugNavTo, !model.benches.isEmpty else { return }
        // A bench id, or "lat,lon" for a stand-in bench (acc's bench set changes between deploys).
        let p = id.split(separator: ",").compactMap { Double($0) }
        let b = model.benches.first { $0.id == id }
            ?? (p.count == 2 ? Bench(id: "debug:\(id)", coordinate: Coordinate(lat: p[0], lon: p[1]), source: .other, backrest: nil) : nil)
        guard let b else { return }
        debugNavDone = true
        nav.preview(b)
    }
}

/// "Offline · laatst bijgewerkt 5 min geleden" when the map shows the cache; nothing when fresh.
struct StatusBanner: View {
    let status: AppModel.Status
    let retry: () -> Void

    var body: some View {
        switch status {
        case .fresh: EmptyView()
        case .loading:
            Label("Bankjes laden…", systemImage: "arrow.triangle.2.circlepath")
                .modifier(BannerStyle(tint: .secondary))
        case .stale(let at):
            Button(action: retry) {
                VStack(alignment: .leading, spacing: 2) {
                    Label("Offline", systemImage: "wifi.slash").font(.subheadline.bold())
                    Text("Laatst bijgewerkt \(at.formatted(.relative(presentation: .named)))")
                        .font(.footnote)
                }
            }
            .buttonStyle(.plain)
            .modifier(BannerStyle(tint: .orange))
            .accessibilityHint(Text("Tik om opnieuw te laden"))
        case .unavailable:
            Button(action: retry) {
                VStack(alignment: .leading, spacing: 2) {
                    Label("Geen verbinding", systemImage: "wifi.slash").font(.subheadline.bold())
                    Text("Bankjes laden zodra je weer online bent. Tik om opnieuw te proberen.").font(.footnote)
                }
            }
            .buttonStyle(.plain)
            .modifier(BannerStyle(tint: .red))
        }
    }
}

struct BannerStyle: ViewModifier {
    let tint: Color
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 14).padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(tint.opacity(0.6)))
            .padding(.horizontal, 12)
    }
}

/// A small "acc" tag on non-production builds, so a screenshot always says which backend it shows.
struct EnvBadge: View {
    let environment: AppEnvironment
    var body: some View {
        if environment != .prd {
            Text(environment.label)
                .font(.caption2.monospaced().bold())
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(.orange.opacity(0.85), in: Capsule())
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, alignment: .trailing)
                .padding(.trailing, 12)
                .accessibilityLabel(Text("Testomgeving \(environment.label)"))
        }
    }
}
