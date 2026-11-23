import BankjesCore
import SwiftUI

extension TravelMode {
    var label: LocalizedStringKey {
        switch self {
        case .foot: return "Lopen"
        case .bike: return "Fietsen"
        case .wheelchair: return "Rolstoel"
        }
    }
    var symbol: String {
        switch self {
        case .foot: return "figure.walk"
        case .bike: return "bicycle"
        case .wheelchair: return "figure.roll"
        }
    }
}

/// The preview sheet: mode picker, distance and ETA, the steps, Start (only with a live fix).
struct NavPreviewSheet: View {
    @Environment(NavigationModel.self) private var nav

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Picker("Vervoerswijze", selection: Binding(get: { nav.mode }, set: { nav.setMode($0) })) {
                        ForEach(TravelMode.allCases, id: \.self) { m in
                            Label(m.label, systemImage: m.symbol).tag(m)
                        }
                    }
                    .pickerStyle(.segmented)
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets())
                }
                switch nav.phase {
                case .loading:
                    Section { HStack { ProgressView(); Text("Route berekenen…").padding(.leading, 8) } }
                case .failed(let problem):
                    NavProblemSection(problem: problem)
                default:
                    if let r = nav.route { summary(r) }
                }
            }
            .listSectionSpacing(.compact)
            .navigationTitle(nav.bench.map { BenchText.title($0) } ?? "")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button { nav.stop() } label: { Image(systemName: "xmark") }
                        .accessibilityLabel(Text("Sluiten"))
                }
            }
        }
    }

    @ViewBuilder private func summary(_ r: Route) -> some View {
        Section {
            HStack(alignment: .firstTextBaseline) {
                Text("\(Geo.formatDistance(r.distanceM)) · \(RouteFormat.duration(r.durationS))")
                    .font(.title2.bold().monospacedDigit())
                Spacer()
                if nav.canStart {
                    Button { nav.start() } label: {
                        Label("Start", systemImage: "location.north.fill").font(.headline).padding(.horizontal, 8)
                    }
                    .buttonStyle(.borderedProminent)
                    .buttonBorderShape(.capsule)
                }
            }
            if !nav.originIsLive {
                Label("Vanaf de Dam: geef locatie-toegang voor live navigatie.", systemImage: "location.slash")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Text(r.engine == "ors" ? "Route via OpenRouteService · open data © OSM" : "Route via OSRM · FOSSGIS · open data © OSM")
                .font(.caption2).foregroundStyle(.secondary)
        }
        Section("Stappen") {
            ForEach(Array(r.steps.enumerated()), id: \.offset) { _, s in
                HStack(alignment: .firstTextBaseline) {
                    Text(s.instruction)
                    Spacer()
                    if s.distanceM > 0 {
                        Text(Geo.formatDistance(s.distanceM)).font(.callout.monospacedDigit()).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }
}

/// Error texts (spec "Errors") with retry and the Open-in-Kaarten escape hatch.
struct NavProblemSection: View {
    @Environment(NavigationModel.self) private var nav
    let problem: RouteProblem

    var body: some View {
        Section {
            VStack(alignment: .leading, spacing: 6) {
                Label(title, systemImage: "exclamationmark.triangle.fill").font(.headline).foregroundStyle(.orange)
                Text(message).font(.subheadline).foregroundStyle(.secondary)
            }
            .padding(.vertical, 4)
            if problem.offersRetry {
                Button { nav.retry() } label: { Label("Opnieuw proberen", systemImage: "arrow.clockwise") }
            }
            if problem.offersMaps {
                Button { nav.openInMaps() } label: { Label("Open in Kaarten", systemImage: "map") }
            }
        }
    }

    private var title: LocalizedStringKey {
        switch problem {
        case .offline: return "Geen verbinding"
        case .wheelchairUnavailable: return "Rolstoelroute niet beschikbaar"
        default: return "Route niet beschikbaar"
        }
    }

    private var message: String {
        switch problem {
        case .outsideArea: return String(localized: "Routes werken alleen in en rond Amsterdam.")
        case .budget: return String(localized: "Het routebudget voor vandaag is op. Probeer het morgen weer, of open de route in Kaarten.")
        case .wheelchairUnavailable(let d): return d ?? String(localized: "Deze server heeft geen rolstoelroutes.")
        case .unavailable(let d): return d ?? String(localized: "Onze routedienst doet het even niet.")
        case .offline: return String(localized: "Je bent offline. Een route berekenen kan alleen met internet.")
        case .other: return String(localized: "Onze routedienst doet het even niet.")
        }
    }
}

/// Live guidance: the current instruction on top, distance / ETA / voice / stop at the bottom.
struct NavLiveOverlay: View {
    @Environment(NavigationModel.self) private var nav

    var body: some View {
        if let f = nav.follower {
            VStack {
                VStack(alignment: .leading, spacing: 6) {
                    Text(f.currentStep?.instruction ?? String(localized: "Volg de route"))
                        .font(.title2.bold())
                        .fixedSize(horizontal: false, vertical: true)
                    if let next = f.nextStep {
                        Group {
                            if let d = f.metresToNextStep {
                                Text("Over \(Geo.formatDistance(d)): \(next.instruction)")
                            } else {
                                Text("Dan: \(next.instruction)")
                            }
                        }
                        .font(.subheadline).foregroundStyle(.secondary)
                    }
                    if nav.rerouting {
                        Label("Route wordt opnieuw berekend…", systemImage: "arrow.triangle.2.circlepath")
                            .font(.footnote).foregroundStyle(.orange)
                    }
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18))
                .padding(.horizontal, 12)
                .accessibilityElement(children: .combine)

                Spacer()

                HStack(spacing: 12) {
                    let rem = f.remaining
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(Geo.formatDistance(rem.metres)) te gaan").font(.headline.monospacedDigit())
                        Text("Aankomst ~\(Date().addingTimeInterval(rem.seconds).formatted(date: .omitted, time: .shortened))")
                            .font(.subheadline.monospacedDigit()).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button { nav.voiceOn.toggle() } label: {
                        Image(systemName: nav.voiceOn ? "speaker.wave.2.fill" : "speaker.slash.fill").frame(width: 28, height: 28)
                    }
                    .buttonStyle(.bordered)
                    .buttonBorderShape(.circle)
                    .accessibilityLabel(Text(nav.voiceOn ? "Spraak uit" : "Spraak aan"))
                    Button(role: .destructive) { nav.stop() } label: { Text("Stop").bold() }
                        .buttonStyle(.borderedProminent)
                        .buttonBorderShape(.capsule)
                        .tint(.red)
                }
                .padding(16)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18))
                .padding(.horizontal, 12)
                .padding(.bottom, 8)
            }
        }
    }
}

/// "Je bent er" (web `navArrive`).
struct NavArrivedCard: View {
    @Environment(NavigationModel.self) private var nav

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: "checkmark.seal.fill").font(.largeTitle).foregroundStyle(Color.accentColor)
            Text("Je bent er!").font(.title2.bold())
            if let b = nav.bench { Text(BenchText.title(b)).foregroundStyle(.secondary) }
            Button { nav.stop() } label: { Text("Klaar").bold().frame(maxWidth: .infinity) }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
        }
        .padding(20)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 20))
        .padding(.horizontal, 12)
        .padding(.bottom, 8)
    }
}
