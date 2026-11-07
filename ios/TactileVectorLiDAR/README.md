# TactileVector native LiDAR companion — source implementation

**Status:** Native Swift source is provided, but not compiled or physically verified here. Requires macOS, Xcode, an iPhone with ARKit `sceneDepth`, Apple code signing and direct-device testing. No iOS Simulator LiDAR.

Native ARKit provides (a) aligned camera buffer, (b) metric scene-depth map, (c) depth confidence, (d) camera tracking pose, and (e) tracked plane anchors classified as floor. This is an experimental local 3D corridor estimator, **not** a verified assistive mobility aid.

1. Install Xcode from the Mac App Store, then `brew install xcodegen`.
2. `cd ~/Code/tactilevector/ios/TactileVectorLiDAR && xcodegen generate && open TactileVectorLiDAR.xcodeproj`
3. In Xcode select project > target > **Signing & Capabilities** > your personal/team development team and change the bundle identifier if needed. Plug the iPhone into the Mac, choose it as the Run destination, approve Developer Mode on the phone if prompted, and click Run.
4. Keep the **same working** Uvicorn HTTPS server (`--host 0.0.0.0 --port 8443`) running on Mac. Ensure the iPhone trusts the development HTTPS certificate already used by Safari. The app **does not bypass TLS verification**.
5. Stop the Safari camera first. Enter `https://YOUR_MAC_WIFI_IP:8443` and the **existing** `TV_API_KEY` in the app. Tap Start + Arm. Slowly sweep the phone over carpet/floor to let ARKit map a classified floor plane. Hold fixed and test an unloaded servo against an unoccupied corridor and chair in a static scene. The app automatically sends 80×60 depth+confidence, camera pose, floor elevation and RGB JPEG at <=3.3 fps.
6. Use **STOP + Neutral** before leaving the app. Going to background requests stop. Firmware's 800 ms independent timeout remains active even if phone traffic stops.

**Why it might abstain:** No classified floor anchor; AR tracking limited; low-confidence depth; phone too tilted; camera farther than ~0.4–1.9 m corridor; insufficient measured floor in any depth band; chair or furniture in a candidate wedge; slow network >500 ms. The system never assumes unseen space is open. Scene-depth values and world pose must share raw ARFrame orientation—do not separately rotate the JPEG or depth.

**Limitations:** No validated localization/navigation, no map persistence, no collision-free guarantee, no stairs/drops/glass handling. ARKit floor classification and 3D geometry can be wrong. This prototype intentionally requires stationary sighted supervision.
