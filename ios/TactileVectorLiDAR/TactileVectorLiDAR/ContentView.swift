import SwiftUI
import ARKit
import SceneKit
import Security

// Store the API key in Keychain, never in UserDefaults or a source file.
private enum TVSecrets {
    private static let service = "org.tactilevector.lidar"
    private static let account = "mac_api_key"

    static func load() -> String {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return "" }
        return String(data: data, encoding: .utf8) ?? ""
    }

    static func save(_ key: String) {
        let lookup: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(lookup as CFDictionary)
        guard !key.isEmpty, let data = key.data(using: .utf8) else { return }
        var insertion = lookup
        insertion[kSecValueData as String] = data
        insertion[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(insertion as CFDictionary, nil)
    }
}

struct ARCameraPreview: UIViewRepresentable {
    let streamer: DepthStreamer

    func makeUIView(context: Context) -> ARSCNView {
        let v = ARSCNView(frame: .zero)
        v.session = streamer.session
        v.scene = SCNScene()
        v.automaticallyUpdatesLighting = true
        return v
    }

    func updateUIView(_ uiView: ARSCNView, context: Context) {}
}

struct ContentView: View {
    @StateObject private var streamer = DepthStreamer()
    @AppStorage("tv.savedMacHTTPS") private var server = ""
    @State private var key = TVSecrets.load()
    @Environment(\.scenePhase) private var phase

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("TactileVector").font(.largeTitle).fontWeight(.bold)
                Text("SPATIAL AWARENESS").font(.caption.weight(.semibold)).tracking(3).foregroundColor(.teal)
                Text("LiDAR obstacle + measured sightline demo · sighted stationary testing only")
                    .font(.caption).foregroundColor(.secondary)
                TextField("Mac HTTPS URL (saved)", text: $server)
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                    .keyboardType(.URL).textFieldStyle(.roundedBorder)
                SecureField("Local access key (saved in Keychain)", text: $key)
                    .textFieldStyle(.roundedBorder)
                Text("Saved Mac address and secure key persist after reopening the app.")
                    .font(.caption2).foregroundColor(.secondary)
                ZStack(alignment: .bottom) {
                    ARCameraPreview(streamer: streamer)
                        .frame(height: 295).clipShape(RoundedRectangle(cornerRadius: 12))
                    Text(streamer.floorDetected ? "LiDAR active · floor reference available" : "LiDAR active · no floor scan required")
                        .font(.caption).padding(8).background(.black.opacity(0.8))
                        .foregroundColor(.white).cornerRadius(6).padding(8)
                }
                HStack {
                    Button("Start + Arm") {
                        Task { await streamer.start(server: server, key: key) }
                    }
                    .buttonStyle(.borderedProminent).disabled(streamer.running)
                    Button("STOP + Neutral") {
                        Task { await streamer.stop() }
                    }
                    .buttonStyle(.bordered).tint(.red)
                }
                Button {
                    Task { await streamer.speakScene() }
                } label: {
                    Label("Describe Scene · Physical Button", systemImage: "speaker.wave.2.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent).tint(.teal)
                .disabled(!streamer.running)
                Text(streamer.narration)
                    .font(.subheadline).foregroundColor(.secondary)
                    .textSelection(.enabled)
                if let image = streamer.sceneImage {
                    Text("CAPTURED SCENE · \(streamer.recognitionStatus)")
                        .font(.caption).foregroundColor(.teal)
                    GeometryReader { geometry in
                        ZStack(alignment: .topLeading) {
                            Image(uiImage: image).resizable().scaledToFit()
                            ForEach(Array(streamer.sceneObjects.enumerated()), id: \.offset) { _, object in
                                if let box = object["box"] as? [Double], box.count == 4 {
                                    Rectangle().stroke(.cyan, lineWidth: 2)
                                        .frame(width: (box[2]-box[0])*geometry.size.width,
                                               height: (box[3]-box[1])*geometry.size.height)
                                        .offset(x: box[0]*geometry.size.width, y: box[1]*geometry.size.height)
                                    Text("\(object["label"] as? String ?? "Object") \(Int((object["confidence"] as? Double ?? 0)*100))%")
                                        .font(.caption2.bold()).padding(3).background(.black.opacity(0.75)).foregroundColor(.white)
                                        .offset(x: box[0]*geometry.size.width, y: box[1]*geometry.size.height)
                                }
                            }
                        }
                    }.aspectRatio(image.size.width / image.size.height, contentMode: .fit)
                    Text("Snapshot from the last description; boxes are not live tracking.")
                        .font(.caption2).foregroundColor(.secondary)
                }
                HStack {
                    Label(streamer.nearestHazard, systemImage: "exclamationmark.triangle")
                    Spacer()
                    Label(streamer.depthQuality, systemImage: "viewfinder")
                }.font(.headline).padding().background(.teal.opacity(0.12)).cornerRadius(12)
                Text(streamer.status).foregroundColor(.primary)
                    .font(.subheadline).textSelection(.enabled)
                HStack {
                    Text("Cue: \(streamer.direction.uppercased())")
                    Spacer()
                    Text("Servo: \(streamer.angle)°")
                }.font(.headline)
                Text("Reason: \(streamer.reason)")
                    .font(.subheadline).textSelection(.enabled)
                Text("Measured depth sightlines L/C/R: \(streamer.lanes)")
                    .font(.caption.monospacedDigit())
                Text("Nearby measured obstacles L/C/R: \(streamer.hazard)")
                    .font(.caption.monospacedDigit())
                Text("Reliable depth samples: \(streamer.depthQuality)")
                    .font(.caption.monospacedDigit())
                Text("No blindfold walking. The system only proposes nearby candidate openings. Glass, drops, traffic, and unobserved space remain hazards.")
                    .font(.caption).foregroundColor(.orange)
            }.padding()
        }
        .tint(.teal)
        .onChange(of: key) { value in
            TVSecrets.save(value)
        }
        .onChange(of: phase) { newPhase in
            if newPhase != .active && streamer.running {
                Task { await streamer.stop() }
            }
        }
    }
}
