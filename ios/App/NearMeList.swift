import BankjesCore
import SwiftUI
import UIKit

/// The 50 benches nearest to you (haversine, on the device; nothing leaves the phone). Without location
/// permission the origin is the Dam, with an explanation. Tap a row to centre the map on that bench.
struct NearMeList: View {
    @Environment(AppModel.self) private var model
    @Environment(LocationProvider.self) private var location
    @Environment(\.dismiss) private var dismiss

    private var origin: Coordinate { location.location ?? .dam }
    private var usingDam: Bool { location.location == nil }
    private var rows: [(bench: Bench, metres: Double)] { Geo.nearest(model.benches, to: origin, limit: 50) }

    var body: some View {
        NavigationStack {
            List {
                if location.isDenied {
                    Section {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Locatie staat uit", systemImage: "location.slash").font(.subheadline.bold())
                            Text("Bankjes mag je locatie niet gebruiken, dus de afstanden zijn gemeten vanaf de Dam. Zet locatie aan in Instellingen om bankjes bij jou in de buurt te zien.")
                                .font(.footnote).foregroundStyle(.secondary)
                            Button("Open Instellingen") {
                                if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                            }
                            .font(.footnote.bold())
                        }
                        .padding(.vertical, 4)
                    }
                } else if usingDam {
                    Section {
                        Label("Locatie zoeken… tot die tijd gemeten vanaf de Dam.", systemImage: "location")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }
                Section {
                    if rows.isEmpty {
                        Text("Nog geen bankjes geladen.").foregroundStyle(.secondary)
                    }
                    ForEach(rows, id: \.bench.id) { row in
                        Button {
                            model.focus = row.bench
                            dismiss()
                        } label: {
                            NearMeRow(bench: row.bench, metres: row.metres)
                        }
                        .buttonStyle(.plain)
                    }
                } header: {
                    Text(usingDam ? "Dichtstbij de Dam" : "Dichtstbij jou")
                }
            }
            .navigationTitle("In de buurt")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Klaar") { dismiss() } }
            }
        }
        .onAppear { location.start() }
        .onDisappear { location.stop() }
    }
}

struct NearMeRow: View {
    let bench: Bench
    let metres: Double

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "chair.lounge.fill")
                .foregroundStyle(.white)
                .frame(width: 32, height: 32)
                .background(Color.accentColor, in: Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(BenchText.title(bench)).font(.body)
                Text(BenchText.source(bench)).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Text(Geo.formatDistance(metres)).font(.callout.monospacedDigit()).foregroundStyle(.secondary)
        }
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityHint(Text("Toon op de kaart"))
    }
}
