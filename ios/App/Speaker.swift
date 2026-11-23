import AVFoundation

/// Dutch voice prompts (web `navSpeak`): nl-NL, each new prompt cuts off the previous one. Decision D2: the
/// audio session ducks other audio (music, podcasts) while a prompt plays and releases it afterwards, and
/// keeps speaking with the screen locked while navigation keeps the app running.
@MainActor
final class Speaker: NSObject, AVSpeechSynthesizerDelegate {
    private let synth = AVSpeechSynthesizer()
    private let voice = AVSpeechSynthesisVoice(language: "nl-NL")
    /// Debug: every prompt spoken, for the simulator run (Console: `log stream --predicate 'subsystem == "bankjes"'`).
    private(set) var spoken: [String] = []

    override init() {
        super.init()
        synth.delegate = self
        synth.usesApplicationAudioSession = true
    }

    func speak(_ text: String) {
        spoken.append(text)
        NSLog("[bankjes-nav] speak: %@", text)
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .voicePrompt, options: [.duckOthers, .interruptSpokenAudioAndMixWithOthers])
        try? session.setActive(true)
        if synth.isSpeaking { synth.stopSpeaking(at: .immediate) }
        let u = AVSpeechUtterance(string: text)
        u.voice = voice
        synth.speak(u)
    }

    func stop() {
        synth.stopSpeaking(at: .immediate)
        release()
    }

    private func release() {
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    nonisolated func speechSynthesizer(_ s: AVSpeechSynthesizer, didFinish u: AVSpeechUtterance) {
        Task { @MainActor in if !self.synth.isSpeaking { self.release() } }
    }
}
