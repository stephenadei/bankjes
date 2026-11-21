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
    // I4 navigation: the route line, follow-the-user while navigating, and the callout's route button.
    var route: [Coordinate]? = nil
    var routeVersion = 0
    var navigating = false
    var fixCount = 0
    var onRoute: (Bench) -> Void = { _ in }

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
        let pan = UIPanGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.userPanned(_:)))
        pan.delegate = context.coordinator
        map.addGestureRecognizer(pan)
        NSLayoutConstraint.activate([
            track.trailingAnchor.constraint(equalTo: map.safeAreaLayoutGuide.trailingAnchor, constant: -12),
            track.bottomAnchor.constraint(equalTo: map.safeAreaLayoutGuide.bottomAnchor, constant: -84),
        ])
        return map
    }

    func updateUIView(_ map: MKMapView, context: Context) {
        let c = context.coordinator
        c.onRoute = onRoute
        updateRoute(map, c)
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

    private func updateRoute(_ map: MKMapView, _ c: Coordinator) {
        if c.routeVersion != routeVersion {
            c.routeVersion = routeVersion
            map.removeOverlays(map.overlays)
            if let route, route.count >= 2 {
                let pts = route.map { CLLocationCoordinate2D(latitude: $0.lat, longitude: $0.lon) }
                let line = MKPolyline(coordinates: pts, count: pts.count)
                map.addOverlay(line, level: .aboveRoads)
                // Preview: the whole route above the sheet. Navigating (a reroute): keep following.
                if !navigating {
                    map.setVisibleMapRect(line.boundingMapRect,
                                          edgePadding: UIEdgeInsets(top: 90, left: 50, bottom: 380, right: 50), animated: true)
                }
            }
        }
        if navigating != c.navigating {
            c.navigating = navigating
            c.lastPan = .distantPast
            if navigating {
                // Street zoom on the start of the walk.
                if let u = map.userLocation.location?.coordinate {
                    map.setCamera(MKMapCamera(lookingAtCenter: u, fromDistance: 700, pitch: 0, heading: 0), animated: true)
                }
            }
        }
        // The map follows you unless you panned in the last 8 s (web: lastUserPan); a pinch zoom is kept.
        if navigating, c.fixCount != fixCount {
            c.fixCount = fixCount
            if Date().timeIntervalSince(c.lastPan) > 8, let u = map.userLocation.location?.coordinate {
                let cam = map.camera.copy() as! MKMapCamera
                cam.centerCoordinate = u
                if cam.centerCoordinateDistance > 3000 { cam.centerCoordinateDistance = 700 }
                map.setCamera(cam, animated: true)
            }
        }
    }

    final class Coordinator: NSObject, MKMapViewDelegate, UIGestureRecognizerDelegate {
        var version = -1
        var byId: [String: BenchAnnotation] = [:]
        var routeVersion = -1
        var navigating = false
        var fixCount = -1
        var lastPan = Date.distantPast
        var onRoute: (Bench) -> Void = { _ in }

        @objc func userPanned(_ g: UIPanGestureRecognizer) {
            if g.state == .began || g.state == .changed { lastPan = Date() }
        }
        func gestureRecognizer(_ g: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer) -> Bool { true }

        func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
            guard let line = overlay as? MKPolyline else { return MKOverlayRenderer(overlay: overlay) }
            let r = MKPolylineRenderer(polyline: line)
            r.strokeColor = UIColor(red: 0x5b / 255, green: 0x7a / 255, blue: 0x3f / 255, alpha: 0.9)   // web route colour
            r.lineWidth = 6
            r.lineCap = .round
            r.lineJoin = .round
            return r
        }

        func mapView(_ mapView: MKMapView, annotationView view: MKAnnotationView, calloutAccessoryControlTapped control: UIControl) {
            guard let b = (view.annotation as? BenchAnnotation)?.bench else { return }
            mapView.deselectAnnotation(view.annotation, animated: true)
            onRoute(b)
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
        let route = UIButton(type: .system)
        route.setImage(UIImage(systemName: "arrow.triangle.turn.up.right.circle.fill",
                               withConfiguration: UIImage.SymbolConfiguration(pointSize: 28)), for: .normal)
        route.sizeToFit()
        route.accessibilityLabel = String(localized: "Route")
        rightCalloutAccessoryView = route
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
