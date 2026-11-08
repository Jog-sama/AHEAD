# Sources reviewed

Reviewed during the Nov 6–7, 2026 Work build. These support API/electrical design choices; none proves the unidentified shield pinout or observed hardware performance.

- [Espressif Arduino LEDC](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html): C3 channels, 1–14-bit resolution, pin-based attach/write API. The build pins Arduino-ESP32 3.2.0.
- [ESP32-C3 datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-c3_datasheet_en.pdf): GPIO restrictions and electrical characteristics. This is chip-level, not SuperMini shield documentation.
- [Tower Pro SG90](https://towerpro.com.tw/product/sg90-7/): external supply, operating voltage and manufacturer comments on current/clone variability. Actual servo identity and load remain unverified.
- [MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia): secure contexts and permissions.
- [WebKit MediaRecorder](https://webkit.org/blog/11353/mediarecorder-api/): recording and MIME feature detection; historical article, so runtime format detection is retained.
- [mkcert official README](https://github.com/FiloSottile/mkcert): local CA, iOS profile/full-trust procedure and private-root-key protection.
- [faster-whisper official repository](https://github.com/SYSTRAN/faster-whisper): optional CPU transcription interface; ASR accuracy not measured.
- [Tinker Inkling cookbook](https://tinker-docs.thinkingmachines.ai/cookbook/inkling/): multimodal/rendering workflow and model example.
- [Tinker models](https://tinker-docs.thinkingmachines.ai/tinker/models/): model listings; verify account accessibility and current naming before integration.
- [Informer developer overview](https://docs.entrinsik.com/developer/): app/API boundaries.
- [Informer webhooks](https://docs.entrinsik.com/developer/guides/magic-apps/webhooks/): deployed handler routes and signed URL token contract.
