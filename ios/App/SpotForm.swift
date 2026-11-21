import BankjesCore
import SwiftUI

/// Add (at a long-press point or the map centre) or edit a Spot: label, description, category.
/// Saving is online only: on failure the form stays open with the error and nothing is kept for later.
struct SpotForm: View {
    enum Mode { case add(Coordinate), edit(Spot) }

    @Environment(SpotsModel.self) private var spots
    @Environment(\.dismiss) private var dismiss
    let mode: Mode
    @State private var draft: SpotDraft
    @State private var busy = false
    @State private var error: String?
    @FocusState private var labelFocused: Bool

    init(mode: Mode) {
        self.mode = mode
        switch mode {
        case .add: _draft = State(initialValue: SpotDraft())
        case .edit(let s): _draft = State(initialValue: SpotDraft(s))
        }
    }

    private var isAdd: Bool { if case .add = mode { return true } else { return false } }
    private var coordinate: Coordinate {
        switch mode {
        case .add(let c): return c
        case .edit(let s): return s.coordinate
        }
    }

    var body: some View {
        NavigationStack {
            Form {
                if let error {
                    Section { SpotErrorView(text: error) }
                }
                Section {
                    TextField("Bijvoorbeeld: bankje aan de gracht", text: $draft.label)
                        .focused($labelFocused)
                        .submitLabel(.next)
                        .accessibilityLabel(Text("Naam"))
                } header: {
                    Text("Naam")
                } footer: {
                    counter(draft.trimmedLabel.count, max: SpotDraft.labelMax,
                            problem: draft.problems.contains(.labelTooLong))
                }
                Section {
                    TextField("Wat maakt dit plekje fijn? (optioneel)", text: $draft.description, axis: .vertical)
                        .lineLimit(3...8)
                        .accessibilityLabel(Text("Beschrijving"))
                } header: {
                    Text("Beschrijving")
                } footer: {
                    counter(draft.trimmedDescription.count, max: SpotDraft.descriptionMax,
                            problem: draft.problems.contains(.descriptionTooLong))
                }
                Section {
                    Picker("Soort", selection: $draft.category) {
                        ForEach(SpotCategory.allCases, id: \.self) { c in
                            Label(SpotText.category(c), systemImage: SpotText.categoryIcon(c)).tag(c)
                        }
                    }
                }
                Section {
                    LabeledContent("Plek") {
                        Text(String(format: "%.5f, %.5f", coordinate.lat, coordinate.lon)).monospacedDigit()
                    }
                } footer: {
                    if isAdd {
                        Text("Nieuwe plekjes zijn privé: alleen jij ziet ze, tot je openbaar maken aanvraagt.")
                    }
                }
            }
            .disabled(busy)
            .navigationTitle(isAdd ? "Nieuw plekje" : "Plekje bewerken")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Annuleer") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    if busy { ProgressView() } else {
                        Button("Bewaar") { save() }.disabled(!draft.isValid)
                    }
                }
            }
            .onAppear { if isAdd { labelFocused = true } }
        }
        .interactiveDismissDisabled(busy)
    }

    private func counter(_ n: Int, max: Int, problem: Bool) -> some View {
        Text("\(n)/\(max)").foregroundStyle(problem ? .red : .secondary).monospacedDigit()
            .frame(maxWidth: .infinity, alignment: .trailing)
    }

    private func save() {
        guard draft.isValid else { return }
        busy = true; error = nil
        Task {
            let e: String?
            switch mode {
            case .add(let c): e = await spots.create(draft, at: c)
            case .edit(let s): e = await spots.update(s, with: draft)
            }
            busy = false
            if let e { error = e } else { dismiss() }
        }
    }
}
