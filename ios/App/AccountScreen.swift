import BankjesCore
import SwiftUI

/// The account sheet: sign in (email → "check your mail") when signed out, the profile with sign out when in.
struct AccountScreen: View {
    @Environment(AuthModel.self) private var auth
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Group {
                if let user = auth.user {
                    ProfileView(user: user)
                } else {
                    SignInView()
                }
            }
            .navigationTitle(auth.isSignedIn ? "Account" : "Inloggen")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Klaar") { dismiss() } }
            }
        }
    }
}

struct SignInView: View {
    @Environment(AuthModel.self) private var auth
    @FocusState private var emailFocused: Bool

    var body: some View {
        @Bindable var auth = auth
        Form {
            if auth.exchanging {
                Section {
                    HStack(spacing: 12) {
                        ProgressView()
                        Text("Bezig met inloggen…")
                    }
                }
            }
            if let notice = auth.notice {
                Section { NoticeView(notice: notice) }
            }
            switch auth.step {
            case .enterEmail:
                Section {
                    TextField("naam@voorbeeld.nl", text: $auth.email)
                        .keyboardType(.emailAddress)
                        .textContentType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .submitLabel(.send)
                        .focused($emailFocused)
                        .onSubmit { Task { await auth.sendLink() } }
                        .accessibilityLabel(Text("E-mailadres"))
                    Button {
                        Task { await auth.sendLink() }
                    } label: {
                        HStack {
                            Text("Stuur inloglink")
                            if auth.busy { Spacer(); ProgressView() }
                        }
                    }
                    .disabled(auth.busy || auth.email.trimmingCharacters(in: .whitespaces).isEmpty)
                } header: {
                    Text("E-mailadres")
                } footer: {
                    Text("Je krijgt een mail met een link. Open die link op deze iPhone om in te loggen; een wachtwoord is niet nodig.")
                }
            case .checkMail(let address):
                Section {
                    VStack(alignment: .leading, spacing: 10) {
                        Label("Check je mail", systemImage: "envelope.badge").font(.headline)
                        Text("We hebben een inloglink gestuurd naar \(address). Tik op de link in de mail op deze iPhone; Bankjes opent dan vanzelf.")
                            .font(.subheadline)
                        Text("Geen mail? Kijk ook in je spam. De link is 30 minuten geldig.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                }
                Section {
                    TimelineView(.periodic(from: .now, by: 1)) { ctx in
                        Button {
                            Task { await auth.resend() }
                        } label: {
                            HStack {
                                Text("Stuur opnieuw")
                                if auth.busy { Spacer(); ProgressView() }
                            }
                        }
                        .disabled(auth.busy || !auth.canResend(at: ctx.date))
                    }
                    Button("Ander e-mailadres") { auth.changeEmail() }
                        .disabled(auth.busy)
                }
            }
        }
        .onAppear { if auth.step == .enterEmail && !auth.exchanging { emailFocused = auth.email.isEmpty } }
    }
}

struct ProfileView: View {
    @Environment(AuthModel.self) private var auth
    let user: AuthUser
    @State private var confirmSignOut = false

    var body: some View {
        Form {
            if let notice = auth.notice {
                Section { NoticeView(notice: notice) }
            }
            Section {
                LabeledContent("Naam", value: user.displayName)
                LabeledContent("E-mailadres", value: user.email)
            } header: {
                Text("Ingelogd")
            } footer: {
                if auth.environment != .prd {
                    Text("Testomgeving \(auth.environment.label)")
                }
            }
            Section {
                Button("Uitloggen", role: .destructive) { confirmSignOut = true }
            }
        }
        .confirmationDialog("Uitloggen?", isPresented: $confirmSignOut, titleVisibility: .visible) {
            Button("Uitloggen", role: .destructive) { auth.signOut() }
            Button("Annuleer", role: .cancel) {}
        }
    }
}

struct NoticeView: View {
    let notice: AuthModel.Notice
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Label {
                Text(notice.text)
            } icon: {
                Image(systemName: notice.kind == .error ? "exclamationmark.triangle.fill" : "info.circle.fill")
                    .foregroundStyle(notice.kind == .error ? .red : .blue)
            }
            .font(.subheadline)
            if let detail = notice.detail {
                Text(detail).font(.caption.monospaced()).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
    }
}

/// The round account button on the map (bottom left, clear of "In de buurt").
struct AccountButton: View {
    @Environment(AuthModel.self) private var auth
    var body: some View {
        @Bindable var auth = auth
        Button { auth.showAccount = true } label: {
            Image(systemName: auth.isSignedIn ? "person.crop.circle.fill" : "person.crop.circle")
                .font(.title2)
                .frame(width: 48, height: 48)
                .background(.regularMaterial, in: Circle())
                .shadow(radius: 3, y: 1)
        }
        .accessibilityLabel(Text(auth.isSignedIn ? "Account" : "Inloggen"))
        .padding(.leading, 16).padding(.bottom, 44)   // above the Maps logo + Legal link
    }
}
