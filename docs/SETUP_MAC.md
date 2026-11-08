# Mac, iPhone, HTTPS, and network setup

## 1. Python

Use Terminal inside the extracted project folder. Homebrew must already be installed; use its official installer if needed.

```bash
brew install python@3.12 mkcert arduino-cli
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock.txt
python scripts/configure.py
python -m pytest -q
open -e .env
```

`configure.py` creates separate random backend and ESP32 tokens, refuses to overwrite `.env`, and sets file mode 0600. Keep `.env`, certificates and firmware `config.h` out of git and sharing. Do not paste sponsor credentials into the phone page. Start in mock mode. The base dependencies are pinned; optional Whisper has its own requirements file.

## 2. Shared network

Use a trusted WPA2/WPA3 personal router/hotspot that allows clients to talk to one another. ESP32-C3 needs 2.4GHz. On an iPhone Personal Hotspot, enable **Maximize Compatibility** if available; verify routing rather than assuming the hotspot-hosting iPhone can reach every client. A second phone/router as hotspot can simplify this. Avoid campus enterprise login/captive portals for the first demo.

Mac and iPhone may use 5GHz on a dual-band router if they remain on the same LAN as the ESP32. Check **AP/client isolation**, guest network isolation, VPN routing, and macOS firewall permissions. Same SSID does not guarantee peer reachability.

Determine the Mac's Wi-Fi address:

```bash
networksetup -listallhardwareports
ipconfig getifaddr en0
```

If Wi-Fi is on `en1` or another interface, use that interface. Record the returned private LAN IP; examples below assign it automatically for en0. Do not treat `192.168.1.123` in the sample .env as your device address.

## 3. Local HTTPS with mkcert

mkcert's CA is for this development setup. Create the certificate for the **actual Mac IP** and only transfer the public root certificate to your iPhone.

```bash
mkcert -install
mkdir -p certs
TV_MAC_IP="$(ipconfig getifaddr en0)"
test -n "$TV_MAC_IP" || { echo "No Wi-Fi address; identify the correct interface first."; exit 1; }
mkcert -cert-file certs/server.pem -key-file certs/server-key.pem localhost 127.0.0.1 "$TV_MAC_IP"
cp "$(mkcert -CAROOT)/rootCA.pem" certs/tactilevector-rootCA.crt
open certs
```

AirDrop **only `tactilevector-rootCA.crt`** to your iPhone. Install the downloaded profile in Settings (typically General → VPN & Device Management / Profile Downloaded). Then Settings → General → About → Certificate Trust Settings → enable full trust for that root. Exact wording can vary by iOS version. **Never transfer `rootCA-key.pem` or `server-key.pem`.** Remove the development CA profile after the demo if no longer needed.

Start one backend worker:

```bash
source .venv/bin/activate
python -m uvicorn backend.app:create_app --factory --host 0.0.0.0 --port 8443 --ssl-certfile certs/server.pem --ssl-keyfile certs/server-key.pem
```

Open **`https://<actual-Mac-IP>:8443` in Safari** on the iPhone, replacing the placeholder. Allow camera/microphone when requested. A warning bypass is not a substitute for a properly trusted certificate. If the Mac IP changes, regenerate the server certificate for its new IP and use that URL; the same trusted root can remain.

The phone calls only this HTTPS origin. Python calls the ESP32 via local HTTP; the browser never makes mixed-content requests. Device tokens are plaintext on the LAN, so use a trusted network. Do not port-forward the servo service or expose it publicly.

## 4. First camera demo

Connect with `TV_API_KEY`, Start camera, choose OpenCV, then Arm. Keep the camera facing the demo surface with a stable orientation. A large green rectangle should occupy at least ~6% of one lower image zone; show it across the lower two-thirds, away from boundaries. Red in the selected zone rejects it. Screen colors/printed colors and room light can shift HSV; start with matte saturated cards in even lighting.

The camera preview is letterboxed rather than cropped; the zone overlay must match the video aspect ratio. Check landscape/portrait alignment on the physical phone. Canvas retains the camera frame aspect ratio and limits its maximum size to 640×480. Do not mirror the camera for direction mapping.

A single frame in flight provides backpressure. The target is **at most 5FPS**, not guaranteed 5FPS. Requests are discarded when stale/busy. Tab backgrounding attempts Stop, but firmware timeout is the backstop when Safari suspends JavaScript. No software timeout is a safety certification.

## 5. Real device mode

After verified wiring and flashing, edit these values in `.env` locally:

```dotenv
TV_DEVICE=esp32
TV_ESP32_URL=http://YOUR_ESP32_IP
TV_DEVICE_TOKEN=THE_SAME_RANDOM_TOKEN_AS_CONFIG_H
TV_LEFT=88
TV_CENTER=90
TV_RIGHT=92
```

The uppercase placeholders are not real values. Copy the token generated in your local `.env` to firmware `DEVICE_TOKEN`. Use the serial console's device IP. Restart Uvicorn after changes. A 503 on Arm means health/neutral acknowledgement failed; don't assume motion occurred. Increase cue separation only after unloaded calibration.

## Troubleshooting

| Symptom | Check |
|---|---|
| Camera/mic button fails | Trusted HTTPS, exact certificate IP, Safari permissions in Settings/site menu, camera not busy in another app |
| UI reachable but camera blocked | `http://LAN-IP` is insecure; `localhost` exception applies only on the same device |
| Certificate warning | Public root profile installed **and** full trust enabled; correct IP in certificate; device clock correct |
| Phone cannot open page | Correct Mac interface/IP, 0.0.0.0 binding, port 8443, firewall allows Python, same LAN, no guest isolation/VPN |
| ESP32 cannot join | 2.4GHz, correct password, no enterprise/captive portal; inspect 115200 baud serial output |
| 401 | Backend key versus device token are separate; compare `.env` and local config |
| 409 | Released/stopped/timed out or changed mode; Arm again; one operator/browser controls at a time |
| Arm expires before input | Start camera before CV Arm; in manual mode press a direction promptly after arming |
| Servo jitters / ESP resets | Remove horn load, check supply under movement, ground continuity, leads and connectors; never “fix” via 3V3 |
| Direction reversed | Verify camera not mirrored; swap calibrated TV_LEFT/TV_RIGHT; don't reverse power wires |
| Green target not detected | Lower camera region, saturated green, adequate size, one zone, even light, no red in selected lane |
| No spoken audio | Tap Speak latest cue, volume/silent settings; speech synthesis is browser dependent; text remains authoritative |
| No microphone transcription | Default is capture-only. Enable optional local ASR or type “status”; no claim audio was understood |

Keep the Mac awake while demonstrating (for example `caffeinate -i` in another Terminal). Turn off automatic screen lock on the demo phone temporarily if appropriate, and restore it afterward. Do not use `--reload` or multiple Uvicorn workers while controlling physical hardware.

## Optional desktop browser regression

With Node installed, `npm install` then `npx playwright install chromium webkit`. In a separate Terminal start the mock backend at port 8765 with the **test-only** key (never reuse this test key for physical hardware):

```bash
TV_DEVICE=mock TV_API_KEY=test-only-backend-key-000000000000 python -m uvicorn backend.app:create_app --factory --host 127.0.0.1 --port 8765
```

Then `npm run test:browser`. The script uses fake camera/mic devices in Chromium and attempts a desktop WebKit page-load check. It does not test iOS permissions, trusted phone HTTPS, or physical hardware. Its screenshot is temporary `/tmp/tv-ui.png`, not a real-camera record.
