import BankjesCore
import SwiftUI

/// "Mijn plekjes": your own Spots with their public status. Signed out, a sign-in prompt instead.
struct SpotsList: View {
    @Environment(SpotsModel.self) private var spots
    @Environment(\.dismiss) private var dismiss
    /// Close this sheet and open the account sheet (two sheets cannot be up at once).
    let signIn: () -> Void
    /// Close this sheet and centre the map on a Spot.
    let show: (Spot) -> Void

    var body: some View {
        NavigationStack {
            List {
                if !spots.isSignedIn {
                    SpotsSignInPrompt(signIn: signIn)
                } else {
                    Section {
                        Button {
                            spots.sheet = .add(spots.mapCentre)
                        } label: {
                            Label("Plekje toevoegen op het midden van de kaart", systemImage: "plus.circle.fill")
                        }
                    } footer: {
                        Text("Of houd je vinger op de kaart om op die plek een plekje toe te voegen.")
                    }
                    Section {
                        if spots.own.isEmpty {
                            Text(spots.loadFailed ? "Je plekjes konden niet worden geladen. Controleer je verbinding."
                                                  : "Je hebt nog geen plekjes.")
                                .foregroundStyle(.secondary)
                        }
                        ForEach(spots.own) { spot in
                            NavigationLink(value: spot.id) { SpotRow(spot: spot) }
                        }
                    } header: {
                        Text("Mijn plekjes")
                    }
                }
            }
            .navigationTitle("Mijn plekjes")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: String.self) { id in SpotDetail(spotId: id, show: show) }
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Klaar") { dismiss() } }
            }
            .refreshable { await spots.load() }
        }
    }
}

struct SpotsSignInPrompt: View {
    let signIn: () -> Void
    var body: some View {
        Section {
            VStack(alignment: .leading, spacing: 10) {
                Label("Log in voor je eigen plekjes", systemImage: "person.crop.circle.badge.plus").font(.headline)
                Text("Met een account bewaar je je eigen plekjes en kun je ze openbaar laten maken. Openbare plekjes van anderen zie je ook zonder account op de kaart.")
                    .font(.subheadline).foregroundStyle(.secondary)
                Button("Inloggen", action: signIn).buttonStyle(.borderedProminent)
            }
            .padding(.vertical, 6)
        }
    }
}

struct SpotRow: View {
    let spot: Spot
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: SpotText.categoryIcon(spot.category))
                .foregroundStyle(.white)
                .frame(width: 34, height: 34)
                .background(Color.spotOwn, in: Circle())
            VStack(alignment: .leading, spacing: 3) {
                Text(spot.label).font(.body)
                HStack(spacing: 6) {
                    Text(SpotText.category(spot.category))
                    Text("·")
                    SpotStatusBadge(status: spot.publicStatus)
                }
                .font(.footnote).foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

struct SpotStatusBadge: View {
    let status: SpotPublicStatus
    var body: some View {
        Label(SpotText.status(status), systemImage: SpotText.statusIcon(status))
            .foregroundStyle(status.tint)
            .labelStyle(.titleAndIcon)
    }
}

/// One own Spot: details, edit, request / revoke public, delete. Another user's public Spot: details only.
struct SpotDetail: View {
    @Environment(SpotsModel.self) private var spots
    @Environment(\.dismiss) private var dismiss
    let spotId: String
    let show: (Spot) -> Void
    @State private var editing = false
    @State private var confirmDelete = false
    @State private var confirmRevoke = false
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        if let spot = spots.spot(spotId) {
            content(spot)
        } else {
            ContentUnavailableView("Dit plekje bestaat niet meer.", systemImage: "mappin.slash")
        }
    }

    private func content(_ spot: Spot) -> some View {
        let own = spots.isOwn(spot)
        return Form {
            if let error {
                Section { SpotErrorView(text: error) }
            }
            Section {
                LabeledContent("Naam", value: spot.label)
                LabeledContent("Soort", value: SpotText.category(spot.category))
                if let d = spot.description, !d.isEmpty {
                    Text(d).font(.subheadline)
                }
                if !own, let name = spot.owner.displayName {
                    LabeledContent("Toegevoegd door", value: name)
                }
                Button { show(spot) } label: { Label("Toon op de kaart", systemImage: "map") }
            }
            if own {
                Section {
                    VStack(alignment: .leading, spacing: 6) {
                        SpotStatusBadge(status: spot.publicStatus).font(.headline)
                        Text(SpotText.statusExplanation(spot.publicStatus)).font(.footnote).foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 2)
                    if spot.canRequestPublic {
                        Button {
                            run { await spots.requestPublic(spot) }
                        } label: {
                            busyLabel("Openbaar maken aanvragen", icon: "globe.europe.africa")
                        }
                    }
                    if spot.canRevokePublic {
                        Button(role: .destructive) { confirmRevoke = true } label: {
                            busyLabel(spot.publicStatus == .requested ? "Aanvraag intrekken" : "Openbaar intrekken",
                                      icon: "arrow.uturn.backward")
                        }
                    }
                } header: {
                    Text("Openbaar")
                } footer: {
                    Text("Een openbaar plekje verschijnt voor iedereen op de kaart, nadat een beheerder het heeft goedgekeurd.")
                }
                Section {
                    Button { editing = true } label: { Label("Bewerken", systemImage: "pencil") }
                    Button(role: .destructive) { confirmDelete = true } label: { Label("Verwijderen", systemImage: "trash") }
                }
            }
        }
        .disabled(busy)
        .navigationTitle(spot.label)
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $editing) { SpotForm(mode: .edit(spot)) }
        .confirmationDialog("\(spot.label) verwijderen?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Verwijderen", role: .destructive) {
                run {
                    let e = await spots.delete(spot)
                    if e == nil { dismiss() }
                    return e
                }
            }
            Button("Annuleer", role: .cancel) {}
        } message: {
            Text("Dit kan niet ongedaan worden gemaakt.")
        }
        .confirmationDialog("Niet meer openbaar?", isPresented: $confirmRevoke, titleVisibility: .visible) {
            Button("Intrekken", role: .destructive) { run { await spots.revokePublic(spot) } }
            Button("Annuleer", role: .cancel) {}
        } message: {
            Text("Het plekje wordt weer privé. Je kunt later opnieuw aanvragen.")
        }
    }

    private func busyLabel(_ title: LocalizedStringKey, icon: String) -> some View {
        HStack {
            Label(title, systemImage: icon)
            if busy { Spacer(); ProgressView() }
        }
    }

    private func run(_ action: @escaping () async -> String?) {
        busy = true; error = nil
        Task {
            error = await action()
            busy = false
        }
    }
}

struct SpotErrorView: View {
    let text: String
    var body: some View {
        Label {
            Text(text)
        } icon: {
            Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.red)
        }
        .font(.subheadline)
        .accessibilityElement(children: .combine)
    }
}

extension SpotPublicStatus {
    var tint: Color {
        switch self {
        case .none, .unknown: return .secondary
        case .requested: return .orange
        case .approved: return .green
        case .denied: return .red
        case .revoked: return .gray
        }
    }
}

extension Color {
    /// Own Spots: purple, clearly apart from the green bench pins.
    static let spotOwn = Color(uiColor: .spotOwn)
    static let spotPublic = Color(uiColor: .spotPublic)
}

extension UIColor {
    static let spotOwn = UIColor.systemPurple
    static let spotPublic = UIColor.systemTeal
}
