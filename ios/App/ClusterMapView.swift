import BankjesCore
import MapKit
import SwiftUI

/// MKMapView wrapper: SwiftUI's `Map` on iOS 17 has no annotation clustering, and ~7,700 benches need it.
struct ClusterMapView: UIViewRepresentable {
    let benches: [Bench]
    let version: Int
    /// A bench to centre on; `focusHandled` is called once it is applied.
    let focus: Bench?
    let focusHandled: () -> Void
    /// I6: own + public Spots (already ACL-filtered), drawn with their own pins, never clustered with benches.
    var spots: [Spot] = []
    var spotsVersion = 0
    var userId: String?
    /// A Spot to centre on ("Toon op de kaart"); `spotFocusHandled` is called once it is applied.
    var spotFocus: Spot?
    var spotFocusHandled: () -> Void = {}
    /// Long-press on the map: add a Spot there.
    var onLongPress: (Coordinate) -> Void = { _ in }
    /// The map centre after every pan/zoom (for "add at the map centre").
    var onCentre: (Coordinate) -> Void = { _ in }
    /// The info button in a Spot's callout.
    var onSpotTapped: (Spot) -> Void = { _ in }

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> MKMapView {
        let map = MKMapView()
        map.delegate = context.coordinator
        map.showsUserLocation = true
        map.pointOfInterestFilter = .excludingAll
        map.showsCompass = true
        map.register(BenchMarkerView.self, forAnnotationViewWithReuseIdentifier: MKMapViewDefaultAnnotationViewReuseIdentifier)
        map.register(BenchClusterView.self, forAnnotationViewWithReuseIdentifier: MKMapViewDefaultClusterAnnotationViewReuseIdentifier)
        let press = UILongPressGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.longPress(_:)))
        press.minimumPressDuration = 0.5
        map.addGestureRecognizer(press)
        map.setRegion(AppConfig.startRegion ?? amsterdamRegion, animated: false)
        let track = MKUserTrackingButton(mapView: map)
        track.translatesAutoresizingMaskIntoConstraints = false
        track.backgroundColor = .systemBackground.withAlphaComponent(0.9)
        track.layer.cornerRadius = 8
        map.addSubview(track)
        NSLayoutConstraint.activate([
            track.trailingAnchor.constraint(equalTo: map.safeAreaLayoutGuide.trailingAnchor, constant: -12),
            track.bottomAnchor.constraint(equalTo: map.safeAreaLayoutGuide.bottomAnchor, constant: -84),
        ])
        return map
    }

    func updateUIView(_ map: MKMapView, context: Context) {
        let c = context.coordinator
        c.parent = self
        if c.spotsVersion != spotsVersion || c.userId != userId {
            c.spotsVersion = spotsVersion; c.userId = userId
            // Diff by id: only Spots that were added, removed or changed are touched.
            var next: [String: SpotAnnotation] = [:]
            var added: [SpotAnnotation] = []
            for s in spots where next[s.id] == nil {
                let own = s.isOwned(by: userId)
                if let old = c.spotsById[s.id], old.spot == s, old.own == own { next[s.id] = old; continue }
                let ann = SpotAnnotation(s, own: own)
                next[s.id] = ann
                added.append(ann)
            }
            let removed = c.spotsById.filter { next[$0.key] !== $0.value }.map(\.value)
            map.removeAnnotations(removed)
            map.addAnnotations(added)
            c.spotsById = next
        }
        if let spot = spotFocus {
            DispatchQueue.main.async { spotFocusHandled() }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.45) {
                let centre = CLLocationCoordinate2D(latitude: spot.coordinate.lat, longitude: spot.coordinate.lon)
                map.setCamera(MKMapCamera(lookingAtCenter: centre, fromDistance: 600, pitch: 0, heading: 0), animated: true)
                if let ann = c.spotsById[spot.id] {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { map.selectAnnotation(ann, animated: true) }
                }
            }
        }
        if c.version != version {
            c.version = version
            let old = map.annotations.compactMap { $0 as? BenchAnnotation }
            map.removeAnnotations(old)
            c.byId = Dictionary(benches.map { ($0.id, BenchAnnotation($0)) }, uniquingKeysWith: { a, _ in a })
            map.addAnnotations(Array(c.byId.values))
        }
        if let bench = focus {
            DispatchQueue.main.async { focusHandled() }
            // Applied after the near-me sheet has gone: a layout change during the dismissal would cut the
            // animation short and leave the map at the old zoom.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.45) {
                let centre = CLLocationCoordinate2D(latitude: bench.coordinate.lat, longitude: bench.coordinate.lon)
                map.setCamera(MKMapCamera(lookingAtCenter: centre, fromDistance: 600, pitch: 0, heading: 0), animated: true)
                if let ann = c.byId[bench.id] {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { map.selectAnnotation(ann, animated: true) }
                }
            }
        }
    }

    final class Coordinator: NSObject, MKMapViewDelegate {
        var version = -1
        var byId: [String: BenchAnnotation] = [:]
        var parent: ClusterMapView?
        var spotsVersion = -1
        var userId: String?
        var spotsById: [String: SpotAnnotation] = [:]

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            if annotation is SpotAnnotation {
                // Not dequeued: a Spot replaced after a write (same place, new annotation) could otherwise get
                // the view of the one being removed and stay hidden. There are only a handful of Spots.
                return SpotMarkerView(annotation: annotation, reuseIdentifier: nil)
            }
            if annotation is BenchAnnotation {
                return mapView.dequeueReusableAnnotationView(withIdentifier: MKMapViewDefaultAnnotationViewReuseIdentifier, for: annotation)
            }
            if annotation is MKClusterAnnotation {
                return mapView.dequeueReusableAnnotationView(withIdentifier: MKMapViewDefaultClusterAnnotationViewReuseIdentifier, for: annotation)
            }
            return nil   // the user location dot
        }

        func mapView(_ mapView: MKMapView, regionDidChangeAnimated animated: Bool) {
            let c = mapView.centerCoordinate
            parent?.onCentre(Coordinate(lat: c.latitude, lon: c.longitude))
        }

        func mapView(_ mapView: MKMapView, annotationView view: MKAnnotationView, calloutAccessoryControlTapped control: UIControl) {
            if let s = view.annotation as? SpotAnnotation { parent?.onSpotTapped(s.spot) }
        }

        @objc func longPress(_ g: UILongPressGestureRecognizer) {
            guard g.state == .began, let map = g.view as? MKMapView else { return }
            let c = map.convert(g.location(in: map), toCoordinateFrom: map)
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
            parent?.onLongPress(Coordinate(lat: c.latitude, lon: c.longitude))
        }
    }
}

final class BenchAnnotation: NSObject, MKAnnotation {
    let bench: Bench
    let coordinate: CLLocationCoordinate2D
    init(_ bench: Bench) {
        self.bench = bench
        coordinate = CLLocationCoordinate2D(latitude: bench.coordinate.lat, longitude: bench.coordinate.lon)
    }
    var title: String? { BenchText.title(bench) }
    var subtitle: String? { BenchText.subtitle(bench) }
}

/// I6: a Spot on the map. Own Spots are purple with a person badge; other users' public Spots teal.
final class SpotAnnotation: NSObject, MKAnnotation {
    let spot: Spot
    let own: Bool
    let coordinate: CLLocationCoordinate2D
    init(_ spot: Spot, own: Bool) {
        self.spot = spot; self.own = own
        coordinate = CLLocationCoordinate2D(latitude: spot.coordinate.lat, longitude: spot.coordinate.lon)
    }
    var title: String? { spot.label }
    var subtitle: String? {
        own ? String(localized: "Mijn plekje · \(SpotText.status(spot.publicStatus))")
            : String(localized: "Openbaar plekje · \(SpotText.category(spot.category))")
    }
}

final class SpotMarkerView: MKMarkerAnnotationView {
    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        canShowCallout = true
        displayPriority = .required
        collisionMode = .circle
        rightCalloutAccessoryView = UIButton(type: .detailDisclosure)
    }
    required init?(coder: NSCoder) { fatalError() }
    override func prepareForDisplay() {
        super.prepareForDisplay()
        clusteringIdentifier = nil
        guard let a = annotation as? SpotAnnotation else { return }
        markerTintColor = a.own ? .spotOwn : .spotPublic
        glyphImage = UIImage(systemName: a.own ? "person.fill" : "star.fill")
        titleVisibility = a.own ? .adaptive : .hidden
        subtitleVisibility = .hidden
        accessibilityLabel = a.own ? String(localized: "Mijn plekje \(a.spot.label)") : String(localized: "Openbaar plekje \(a.spot.label)")
    }
}

final class BenchMarkerView: MKMarkerAnnotationView {
    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        clusteringIdentifier = "bench"
        markerTintColor = UIColor(named: "AccentColor")
        glyphImage = UIImage(systemName: "chair.lounge.fill")
        displayPriority = .defaultLow
        canShowCallout = true
        titleVisibility = .hidden
        subtitleVisibility = .hidden
        collisionMode = .circle
    }
    required init?(coder: NSCoder) { fatalError() }
    override func prepareForDisplay() {
        super.prepareForDisplay()
        clusteringIdentifier = "bench"
        markerTintColor = UIColor(named: "AccentColor")
    }
}

final class BenchClusterView: MKMarkerAnnotationView {
    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        markerTintColor = UIColor(named: "AccentColor")
        displayPriority = .defaultHigh
        titleVisibility = .hidden
        subtitleVisibility = .hidden
        canShowCallout = true
        collisionMode = .circle
    }
    required init?(coder: NSCoder) { fatalError() }
    override func prepareForDisplay() {
        super.prepareForDisplay()
        markerTintColor = UIColor(named: "AccentColor")
        if let cluster = annotation as? MKClusterAnnotation {
            let n = cluster.memberAnnotations.count
            glyphText = n >= 1000 ? "\(n / 1000)k" : "\(n)"
            cluster.title = String(localized: "\(n) bankjes")
            cluster.subtitle = nil
        }
    }
}

/// Labels for one bench, Dutch-first.
enum BenchText {
    static func title(_ b: Bench) -> String {
        switch b.backrest {
        case true?: return String(localized: "Bankje met rugleuning")
        case false?: return String(localized: "Bankje zonder rugleuning")
        case nil: return String(localized: "Bankje")
        }
    }
    static func source(_ b: Bench) -> String {
        switch b.source {
        case .bgt: return String(localized: "Gemeente (BGT)")
        case .osm: return "OpenStreetMap"
        case .other: return String(localized: "Onbekende bron")
        }
    }
    static func subtitle(_ b: Bench) -> String { source(b) }
}
