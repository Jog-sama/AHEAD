import Foundation
import ARKit
import CoreImage
import UIKit
import AVFoundation
import Combine
import QuartzCore

/// Collects synchronized sensor frames. No server credentials are persisted.
/// Never disables HTTPS trust checks. The Mac's trusted mkcert CA must be installed.
final class DepthStreamer: NSObject, ObservableObject, ARSessionDelegate {
    let session = ARSession()
    @Published var status = "Enter Mac HTTPS URL and key, then Start + Arm."
    @Published var direction = "unknown"
    @Published var angle = 90
    @Published var reason = "Not running"
    @Published var lanes = "— / — / —"
    @Published var floorDetected = false
    @Published var hazard = "— / — / —"
    @Published var depthQuality = "—"
    @Published var running = false
    @Published var narration = "Physical button: speak a scene description."
    @Published var sceneImage: UIImage?
    @Published var sceneObjects: [[String: Any]] = []
    @Published var recognitionStatus = "Tap Describe Scene to capture objects."
    @Published var nearestHazard = "—"
    private var buttonTask: Task<Void, Never>?
    private var narrationInFlight = false
    private let speaker = AVSpeechSynthesizer()

    private struct Connection {
        let baseURL: URL
        let key: String
        let generation: Int
    }
    private let captureQueue = DispatchQueue(label: "org.tactilevector.arkit.capture")
    private let ciContext = CIContext(options: [.useSoftwareRenderer: false])
    private var current: Connection?
    // All below session fields are accessed only on captureQueue, except via sync.
    private var pending: Connection?
    private var armingInFlight = false
    private var sessionEpoch = 0
    private var consecutiveNetworkErrors = 0
    private var frameInFlight = false
    private var nextCapture: TimeInterval = 0
    private var sequence = 0

    override init() {
        super.init()
        session.delegate = self
        session.delegateQueue = captureQueue
    }

    private func endpoint(_ base: URL, path: String, query: String = "") -> URL {
        var components = URLComponents(url: base, resolvingAgainstBaseURL: false)!
        let basePath = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        components.path = "/" + ([basePath, path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))]
            .filter { !$0.isEmpty }.joined(separator: "/"))
        components.percentEncodedQuery = query.isEmpty ? nil : query
        return components.url!
    }

    private func post(_ path: String, body: Data, conn: Connection, query: String = "") async throws -> [String: Any] {
        var req = URLRequest(url: endpoint(conn.baseURL, path: path, query: query))
        req.httpMethod = "POST"
        req.httpBody = body
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(conn.key, forHTTPHeaderField: "X-API-Key")
        req.timeoutInterval = path == "api/voice/scene" ? 15.0 : 2.0
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
            throw NSError(domain: "TactileVector", code: statusCode,
                          userInfo: [NSLocalizedDescriptionKey: "Mac endpoint returned HTTP \(statusCode)"])
        }
        return (try JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
    }

    private func get(_ path: String, conn: Connection) async throws -> [String: Any] {
        var req = URLRequest(url: endpoint(conn.baseURL, path: path))
        req.httpMethod = "GET"
        req.setValue(conn.key, forHTTPHeaderField: "X-API-Key")
        req.timeoutInterval = 1.2
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw NSError(domain: "TactileVector", code: (response as? HTTPURLResponse)?.statusCode ?? 0)
        }
        return (try JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
    }

    /// Higher-quality RGB is captured ONLY for a spoken description. Navigation
    /// continues to stream its original small JPEG/depth packet unchanged.
    private func sceneSnapshotJPEG() -> Data? {
        guard let frame = session.currentFrame else { return nil }
        let buffer = frame.capturedImage
        let width = CVPixelBufferGetWidth(buffer)
        let original = CIImage(cvPixelBuffer: buffer)
        let scale = min(1.0, 1120.0 / CGFloat(width))
        let image = original.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        guard let cg = ciContext.createCGImage(image, from: image.extent) else { return nil }
        guard let jpeg = UIImage(cgImage: cg).jpegData(compressionQuality: 0.76),
              jpeg.count < 800_000 else { return nil }
        return jpeg
    }

    /// RGB object names are computed on the Mac on demand, with LiDAR depth
    /// associated to each detected image region. No motor commands here.
    @MainActor
    func speakScene() async {
        guard !narrationInFlight else { return }
        guard let conn = captureQueue.sync(execute: { self.current }), running else {
            narration = "Start + Arm first; a fresh scene is required."
            return
        }
        narrationInFlight = true
        narration = "Analyzing RGB objects and LiDAR distances on Mac..."
        defer { narrationInFlight = false }
        do {
            guard let frame = session.currentFrame,
                  CACurrentMediaTime() - frame.timestamp < 0.4,
                  let packetData = makePayload(frame: frame, sceneQuality: true),
                  let packet = try JSONSerialization.jsonObject(with: packetData) as? [String: Any],
                  let encoded = packet["jpeg_b64"] as? String,
                  let imageData = Data(base64Encoded: encoded) else {
                narration = "Waiting for fresh camera and LiDAR. Try again."
                return
            }
            let payload = try JSONSerialization.data(withJSONObject: ["packet": packet])
            let result = try await post("api/voice/scene", body: payload, conn: conn)
            guard running && captureQueue.sync(execute: { self.current?.generation == conn.generation }) else { return }
            let phrase = result["phrase"] as? String ?? "No current scene description."
            narration = phrase
            sceneImage = UIImage(data: imageData)
            sceneObjects = result["objects"] as? [[String: Any]] ?? []
            if let diagnostics = result["diagnostics"] as? [String: Any] {
                recognitionStatus = "\(sceneObjects.count) objects · \(diagnostics["inference_ms"] ?? "—") ms · captured scene"
                let turns = diagnostics["upright_quarter_turns"] as? Int ?? 0
                if turns > 0, let cg = sceneImage?.cgImage {
                    let orientation: UIImage.Orientation = turns == 1 ? .left : turns == 2 ? .down : .right
                    let oriented = UIImage(cgImage: cg, scale: 1, orientation: orientation)
                    let size = turns % 2 == 0 ? CGSize(width: cg.width, height: cg.height) : CGSize(width: cg.height, height: cg.width)
                    sceneImage = UIGraphicsImageRenderer(size: size).image { _ in oriented.draw(in: CGRect(origin: .zero, size: size)) }
                    sceneObjects = sceneObjects.map { object in
                        var updated = object
                        if var b = object["box"] as? [Double], b.count == 4 {
                            for _ in 0..<turns { b = [b[1], 1-b[2], b[3], 1-b[0]] }
                            updated["box"] = b
                        }
                        return updated
                    }
                }
            }
            if let warning = result["model_warning"] as? String { recognitionStatus = warning }
            speaker.stopSpeaking(at: .immediate)
            try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
            try? AVAudioSession.sharedInstance().setActive(true)
            let utterance = AVSpeechUtterance(string: phrase)
            utterance.rate = 0.48
            speaker.speak(utterance)
        } catch {
            narration = "Scene narration unavailable: \(error.localizedDescription)"
            // This is NOT a navigation failure: never stop or rearm the servo
            // just because RGB narration is unavailable.
        }
    }

    /// The physical ESP32 button increments a monotonic event counter. The
    /// first observed value is a baseline, not an old press to replay.
    @MainActor
    private func pollPhysicalButton() async {
        var prior: Int?
        var generation: Int?
        while running && !Task.isCancelled {
            if let conn = captureQueue.sync(execute: { self.current }) {
                if generation != conn.generation {
                    generation = conn.generation
                    prior = nil
                }
                do {
                    let result = try await get("api/button", conn: conn)
                    if let count = result["press_count"] as? Int, count >= 0 {
                        if let previous = prior, count != previous {
                            // The firmware counter wraps at 2^32. One or more
                            // new presses request a single fresh description.
                            prior = count
                            await speakScene()
                        } else {
                            prior = count
                        }
                    }
                } catch {
                    // A momentary poll failure must not interrupt navigation.
                    // On reconnect we rebaseline, avoiding stale press replay.
                    prior = nil
                }
            }
            try? await Task.sleep(nanoseconds: 450_000_000)
        }
    }

    @MainActor
    func start(server: String, key: String) async {
        guard !running else { return }
        guard let url = URL(string: server), url.scheme == "https", url.host != nil,
              !key.isEmpty else {
            status = "Enter HTTPS Mac URL and the dashboard's existing API key."
            return
        }
        guard ARWorldTrackingConfiguration.isSupported,
              (ARWorldTrackingConfiguration.supportsFrameSemantics(.smoothedSceneDepth)
               || ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth)) else {
            status = "This iPhone does not expose ARKit LiDAR scene depth. Use Safari fallback."
            return
        }
        // Start the camera first and arm only once tracked depth frames arrive;
        // arming before ARKit is ready lets the server watchdog expire the generation.
        let initial = Connection(baseURL: url, key: key, generation: 0)
        captureQueue.sync {
            self.sessionEpoch += 1
            self.pending = initial
            self.current = nil
            self.armingInFlight = false
            self.frameInFlight = false
            self.nextCapture = 0
            self.sequence = 0
            self.consecutiveNetworkErrors = 0
        }
        let config = ARWorldTrackingConfiguration()
        config.planeDetection = [.horizontal]
        config.environmentTexturing = .none
        config.frameSemantics = ARWorldTrackingConfiguration.supportsFrameSemantics(.smoothedSceneDepth)
            ? [.smoothedSceneDepth] : [.sceneDepth]
        session.run(config, options: [.resetTracking, .removeExistingAnchors])
        running = true
        buttonTask?.cancel()
        buttonTask = Task { await self.pollPhysicalButton() }
        status = "Preparing LiDAR. Steering will arm when tracked depth is ready."
    }

    @MainActor
    func stop() async {
        session.pause()
        running = false
        buttonTask?.cancel()
        buttonTask = nil
        speaker.stopSpeaking(at: .immediate)
        direction = "unknown"
        reason = "Stopped"
        angle = 90
        let conn: Connection? = captureQueue.sync {
            let value = self.current ?? self.pending
            self.sessionEpoch += 1
            self.current = nil
            self.pending = nil
            self.armingInFlight = false
            self.frameInFlight = false
            return value
        }
        if let conn = conn {
            do {
                _ = try await post("api/stop", body: Data("{}".utf8), conn: conn)
                status = "Stopped and requested neutral from Mac."
            } catch {
                status = "STOP request failed; independent ESP32 neutral timeout remains."
            }
        } else {
            status = "Stopped."
        }
    }

    private func endExpiredSession(epoch: Int, detail: String) {
        // captureQueue only. DO NOT automatically re-arm after HTTP 409 or
        // network loss: explicit user action is required for a new session.
        guard sessionEpoch == epoch else { return }
        sessionEpoch += 1
        current = nil
        pending = nil
        frameInFlight = false
        armingInFlight = false
        session.pause()
        DispatchQueue.main.async {
            self.running = false
            self.buttonTask?.cancel()
            self.buttonTask = nil
            self.speaker.stopSpeaking(at: .immediate)
            self.direction = "unknown"
            self.angle = 90
            self.reason = "Session ended"
            self.status = detail
        }
    }

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        // All session protocol state is owned by the ARSession delegate queue.
        if current == nil {
            guard let candidate = pending, !armingInFlight,
                  (frame.smoothedSceneDepth ?? frame.sceneDepth) != nil else { return }
            guard case .normal = frame.camera.trackingState else { return }
            armingInFlight = true
            let epoch = sessionEpoch
            Task {
                do {
                    let state = try await self.post("api/arm",
                        body: Data(#"{"mode":"obstacle"}"#.utf8), conn: candidate)
                    guard let gen = state["generation"] as? Int else {
                        throw NSError(domain: "TactileVector", code: 0,
                                      userInfo: [NSLocalizedDescriptionKey: "Missing generation"])
                    }
                    let connection = Connection(baseURL: candidate.baseURL,
                        key: candidate.key, generation: gen)
                    self.captureQueue.async {
                        if self.sessionEpoch == epoch && self.pending != nil {
                            self.current = connection
                            self.pending = nil
                            self.armingInFlight = false
                            self.frameInFlight = false
                            self.sequence = 0
                            self.nextCapture = 0
                            DispatchQueue.main.async {
                                self.status = "LiDAR streaming. Mac controller armed."
                            }
                        } else {
                            // STOP happened while /arm was in flight. Neutralize
                            // the newly armed generation instead of leaving it live.
                            Task { _ = try? await self.post("api/stop",
                                body: Data("{}".utf8), conn: connection) }
                        }
                    }
                } catch {
                    self.captureQueue.async {
                        self.endExpiredSession(epoch: epoch,
                            detail: "Cannot arm Mac: \(error.localizedDescription). Check HTTPS/key and retry.")
                    }
                }
            }
            return
        }
        guard let conn = current, !frameInFlight,
              CACurrentMediaTime() >= nextCapture else { return }
        frameInFlight = true
        nextCapture = CACurrentMediaTime() + 0.25
        sequence += 1
        let seq = sequence
        let epoch = sessionEpoch
        guard let payload = makePayload(frame: frame) else {
            frameInFlight = false
            return
        }
        Task {
            do {
                let output = try await self.post("api/arkit/frame", body: payload, conn: conn,
                    query: "generation=\(conn.generation)&sequence=\(seq)")
                self.captureQueue.async {
                    guard self.sessionEpoch == epoch else { return }
                    self.consecutiveNetworkErrors = 0
                    self.frameInFlight = false
                    DispatchQueue.main.async {
                        self.direction = output["direction"] as? String ?? "unknown"
                        self.angle = output["commanded_angle"] as? Int ?? 90
                        let vision = output["vision"] as? [String: Any]
                        self.reason = vision?["reason"] as? String ?? "No scene reasoning"
                        if let scene = vision?["scene"] as? [String: Any],
                           let free = scene["free_space"] as? [String: Double] {
                            self.lanes = String(format: "%.0f / %.0f / %.0f",
                                (free["left"] ?? 0)*100,
                                (free["center"] ?? 0)*100,
                                (free["right"] ?? 0)*100)
                        }
                        if let scene = vision?["scene"] as? [String: Any] {
                            if let distances = scene["nearest_obstacle_m"] as? [String: Any] {
                                let values = distances.values.compactMap { $0 as? Double }
                                self.nearestHazard = values.min().map { String(format: "%.1f m", $0) } ?? "Not measured"
                            }
                            if let blocked = scene["near_obstacles"] as? [String: Bool] {
                                self.hazard = ["left", "center", "right"]
                                    .map { blocked[$0] == true ? "BLOCK" : "—" }.joined(separator: " / ")
                            }
                            if let quality = scene["valid_depth_fraction"] as? Double {
                                self.depthQuality = String(format: "%.0f%%", quality * 100)
                            }
                        }
                        self.status = output["phrase"] as? String ?? "Frame accepted"
                    }
                }
            } catch {
                self.captureQueue.async {
                    guard self.sessionEpoch == epoch else { return }
                    self.frameInFlight = false
                    let code = (error as NSError).code
                    if code == 429 || code == 408 {
                        // Busy/late frame: drop, do not queue and do not spam UI.
                        return
                    }
                    self.consecutiveNetworkErrors += 1
                    if code == 409 || code == 401 || self.consecutiveNetworkErrors >= 2 {
                        let reason = code == 409
                            ? "Session expired; stopped streaming. Tap Start + Arm to restart."
                            : "Connection failed; stopped safely. Check server and retry."
                        self.endExpiredSession(epoch: epoch, detail: reason)
                    }
                }
            }
        }
    }

    private func makePayload(frame: ARFrame, sceneQuality: Bool = false) -> Data? {
        guard let depth = frame.smoothedSceneDepth ?? frame.sceneDepth else { return nil }
        let dp = depth.depthMap
        let cp = depth.confidenceMap
        guard CVPixelBufferGetPixelFormatType(dp) == kCVPixelFormatType_DepthFloat32 else { return nil }

        let anchors = frame.anchors.compactMap { $0 as? ARPlaneAnchor }
            .filter { $0.alignment == .horizontal && $0.classification == .floor }
        let floorY = anchors.max(by: {
            $0.extent.x * $0.extent.z < $1.extent.x * $1.extent.z
        })?.transform.columns.3.y
        DispatchQueue.main.async { self.floorDetected = floorY != nil }

        let captured = frame.capturedImage
        let iw = CVPixelBufferGetWidth(captured), ih = CVPixelBufferGetHeight(captured)
        let original = CIImage(cvPixelBuffer: captured)
        // No portrait rotation: sensor pixels, intrinsics and depth must stay aligned.
        let scale = min(1.0, (sceneQuality ? 1120.0 : 640.0) / CGFloat(iw))
        let scaled = original.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        guard let cg = ciContext.createCGImage(scaled, from: scaled.extent),
              let jpeg = UIImage(cgImage: cg).jpegData(compressionQuality: sceneQuality ? 0.76 : 0.49),
              jpeg.count < 400_000 else { return nil }

        let dw = CVPixelBufferGetWidth(dp), dh = CVPixelBufferGetHeight(dp)
        CVPixelBufferLockBaseAddress(dp, .readOnly)
        if let cp = cp { CVPixelBufferLockBaseAddress(cp, .readOnly) }
        defer {
            CVPixelBufferUnlockBaseAddress(dp, .readOnly)
            if let cp = cp { CVPixelBufferUnlockBaseAddress(cp, .readOnly) }
        }
        guard let dbase = CVPixelBufferGetBaseAddress(dp) else { return nil }
        let dptr = dbase.assumingMemoryBound(to: Float32.self)
        let dstride = CVPixelBufferGetBytesPerRow(dp) / MemoryLayout<Float32>.stride
        let cptr = cp.flatMap { CVPixelBufferGetBaseAddress($0) }?.assumingMemoryBound(to: UInt8.self)
        let cstride = cp.map { CVPixelBufferGetBytesPerRow($0) } ?? 0
        let cw = cp.map { CVPixelBufferGetWidth($0) } ?? 0
        let ch = cp.map { CVPixelBufferGetHeight($0) } ?? 0
        let width = 80, height = 60
        var distance = [Float](repeating: 0, count: width*height)
        var confidence = [Int](repeating: 0, count: width*height)
        for y in 0..<height {
            let sy = min(dh-1, Int((Double(y)+0.5)*Double(dh)/Double(height)))
            for x in 0..<width {
                let sx = min(dw-1, Int((Double(x)+0.5)*Double(dw)/Double(width)))
                let value = dptr[sy*dstride+sx]
                let index = y*width+x
                distance[index] = value.isFinite && value > 0 && value < 10 ? value : 0
                if let cptr = cptr, cw > 0, ch > 0 {
                    let cx = min(cw-1, Int((Double(x)+0.5)*Double(cw)/Double(width)))
                    let cy = min(ch-1, Int((Double(y)+0.5)*Double(ch)/Double(height)))
                    confidence[index] = min(2, Int(cptr[cy*cstride+cx]))
                } else { confidence[index] = 0 } // Never assume missing confidence is high.
            }
        }
        let intr = frame.camera.intrinsics
        let t = frame.camera.transform
        let pose: [Float] = [t.columns.0.x,t.columns.0.y,t.columns.0.z,t.columns.0.w,
                              t.columns.1.x,t.columns.1.y,t.columns.1.z,t.columns.1.w,
                              t.columns.2.x,t.columns.2.y,t.columns.2.z,t.columns.2.w,
                              t.columns.3.x,t.columns.3.y,t.columns.3.z,t.columns.3.w]
        let tracking: String
        switch frame.camera.trackingState {
        case .normal: tracking = "normal"
        case .limited: tracking = "limited"
        case .notAvailable: tracking = "not_available"
        @unknown default: tracking = "limited"
        }
        var data: [String: Any] = [
            "jpeg_b64": jpeg.base64EncodedString(),
            "image_width": iw, "image_height": ih,
            "depth_width": width, "depth_height": height,
            "depth_m": distance, "confidence": confidence,
            "intrinsics": [intr.columns.0.x, intr.columns.1.y, intr.columns.2.x, intr.columns.2.y],
            "camera_to_world": pose, "tracking": tracking,
        ]
        if let floorY = floorY { data["floor_y_world"] = floorY }
        return try? JSONSerialization.data(withJSONObject: data)
    }
}
