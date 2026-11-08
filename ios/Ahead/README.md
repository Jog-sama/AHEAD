# Ahead, the iPhone app's page

`index.html` is the whole interface of the Ahead app: the walk screen, the cane and the thumb lever over Bluetooth, push-to-ask, the
settings and the computer mirror. The native shell that runs it, a web view with a bridge to the phone's LiDAR,
haptics, Bluetooth, speech and camera, is the `Ahead` target of jonasneves/phone-bridge (private; ask Jonas for
access), which copies this file into the app bundle at build time from a checkout of this repo beside it:

```sh
~/github.com/Jog-sama/AHEAD             # this repo
~/github.com/jonasneves/phone-bridge    # the shell; ./install.sh Ahead, ./testflight.sh Ahead
```

A push to `main` that changes this file also publishes it at https://jonasneves.com/bridge/ahead/ through
`.github/workflows/pages-ahead.yml`, which is the copy a computer opens to watch a phone (`?watch=<code>`).
The phone runs the bundled copy, so a change reaches it with the next install, not the push.

The calls it makes (`depth.start`, `haptics.pattern`, `ble.*`, `live.*` and the rest) are documented in phone-bridge's
AGENTS.md. Testers install the app from TestFlight: https://testflight.apple.com/join/RuyPSTNZ.
