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

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> MKMapView {
        let map = MKMapView()
        map.delegate = context.coordinator
        map.showsUserLocation = true
        map.pointOfInterestFilter = .excludingAll
        map.showsCompass = true
        map.register(BenchMarkerView.self, forAnnotationViewWithReuseIdentifier: MKMapViewDefaultAnnotationViewReuseIdentifier)
        map.register(BenchClusterView.self, forAnnotationViewWithReuseIdentifier: MKMapViewDefaultClusterAnnotationViewReuseIdentifier)
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
