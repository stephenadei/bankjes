import BankjesCore
import MapKit
import SwiftUI

/// Amsterdam at city zoom, centred on the Dam.
let amsterdamRegion = MKCoordinateRegion(
    center: CLLocationCoordinate2D(latitude: Coordinate.dam.lat, longitude: Coordinate.dam.lon),
    span: MKCoordinateSpan(latitudeDelta: 0.12, longitudeDelta: 0.12))

struct MapScreen: View {
    @Environment(AppModel.self) private var model
    @Environment(SpotsModel.self) private var spots
    @Environment(AuthModel.self) private var auth
    @Environment(\.scenePhase) private var scenePhase
    @State private var showNearMe = false
    @State private var spotFocus: Spot?

    var body: some View {
        // Reading model.focus here (not a binding) is what makes the view update when the list sets it.
        @Bindable var spots = spots
        ClusterMapView(benches: model.benches, version: model.benchesVersion, focus: model.focus,
                       focusHandled: { model.focus = nil },
                       spots: spots.spots, spotsVersion: spots.version, userId: auth.user?.id,
                       spotFocus: spotFocus, spotFocusHandled: { spotFocus = nil },
                       onLongPress: { c in
                           // Signed out: the list sheet shows the sign-in prompt instead of the form.
                           spots.sheet = spots.isSignedIn ? .add(c) : .list
                       },
                       onCentre: { spots.mapCentre = $0 },
                       onSpotTapped: { spots.sheet = .detail($0.id) })
            .ignoresSafeArea()
            .overlay(alignment: .top) {
                VStack(spacing: 6) {
                    EnvBadge(environment: model.environment)
                    StatusBanner(status: model.status, retry: { Task { await model.load() } })
                }
            }
            .overlay(alignment: .bottom) {
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
            .overlay(alignment: .bottomLeading) {
                Button { spots.sheet = .list } label: {
                    Image(systemName: "mappin.and.ellipse")
                        .font(.title2)
                        .foregroundStyle(Color.spotOwn)
                        .frame(width: 48, height: 48)
                        .background(.regularMaterial, in: Circle())
                        .shadow(radius: 3, y: 1)
                }
                .accessibilityLabel(Text("Mijn plekjes"))
                .padding(.leading, 16).padding(.bottom, 100)   // above the account button
            }
            .sheet(isPresented: $showNearMe) {
                NearMeList().presentationDetents([.medium, .large])
            }
            .sheet(item: $spots.sheet) { sheet in
                switch sheet {
                case .list:
                    SpotsList(signIn: signInFromSheet, show: showOnMap)
                case .add(let c):
                    SpotForm(mode: .add(c))
                case .detail(let id):
                    NavigationStack {
                        SpotDetail(spotId: id, show: showOnMap)
                            .toolbar {
                                ToolbarItem(placement: .confirmationAction) { Button("Klaar") { spots.sheet = nil } }
                            }
                    }
                    .presentationDetents([.medium, .large])
                }
            }
            .task { await model.load() }
            // Spots follow the account: reload on sign-in / sign-out (and at launch).
            .task(id: auth.user?.id) {
                if auth.user == nil { spots.signedOut() }
                await spots.load()
            }
            .onAppear {
                spots.onSignedOut = {
                    // The 401 closed the Spots sheet; open sign-in once it is gone.
                    auth.showAccount = false
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { auth.showAccount = true }
                }
            }
            .onChange(of: scenePhase) { _, phase in
                // Back from the background with a stale map: try again.
                if phase == .active, case .stale = model.status { Task { await model.load() } }
            }
    }
}

extension MapScreen {
    private func signInFromSheet() {
        spots.sheet = nil
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { auth.showAccount = true }
    }

    private func showOnMap(_ spot: Spot) {
        spots.sheet = nil
        spotFocus = spot
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
