# Optional voice, neural vision, and sponsor extensions

## Voice, default behaviour

The base UI provides concise spoken status through browser speech synthesis. Text is always visible; a separate Speak button lets the user retry under Safari's user-gesture restrictions. It accepts typed “status”, “clear path”, “what is ahead” and “what's ahead”. Unknown questions return “Object finding unavailable in baseline.” There is no invented distance or door detection.

Hold-to-record requests microphone permission only on press, negotiates a MediaRecorder MIME supported by the browser, records up to four seconds, and uploads to Python. The server defaults to **capture receipt only** and explicitly returns `transcription:null`; it does not pretend the audio was understood. Audio is not saved. The phone keeps a local playback blob until the next recording/page close.

For local speech recognition, use the implemented optional adapter:

```bash
source .venv/bin/activate
python -m pip install -r requirements-voice.txt
python -c 'from faster_whisper import WhisperModel; WhisperModel("tiny.en", device="cpu", compute_type="int8", download_root="models")'
```

This explicit preparation command downloads model weights from the model host; review that dependency and allow time/network access. Locate the model snapshot folder containing `model.bin` (not the outer cache folder), and set `TV_WHISPER_MODEL` in ignored `.env` to its **absolute path**. Restart the backend. Runtime uses `local_files_only=True`, CPU int8, and at most two CPU threads; no automatic model download in the request path. Apple Silicon is supported by the underlying CPU dependencies subject to wheel availability; this is not a Metal GPU integration.

The adapter decodes a maximum eight seconds of audio, transcribes off the async event loop, serializes speech requests, and passes recognized text through the same short-rule answer path. Speech does not send motor commands. If transcription takes long enough that camera input expires, the response says input is stale/disarmed. Do not increase actuation timeouts to mask slow speech.

No real microphone utterance/model inference was tested unless explicitly recorded in the verification report. The injected transcriber test validates plumbing, not ASR accuracy. If optional dependencies/model download fail, keep the working camera/control demo and use typed/read status.

## Neural vision boundary

`VisionAdapter.predict(jpeg) -> Decision` is the implemented interface. `create_app(vision=...)` allows dependency injection. No neural model is installed or auto-downloaded by the base requirements. DepthAnythingV2, YOLO, or MediaPipe are future plug-ins, not fake enabled features.

A useful next implementation is a separate local module/worker that returns direction, reason and short phrase. Keep it out of the firmware. Preserve unknown→neutral, stale-generation checks, time budget and command bounds. Evaluate on held-out recordings, including blank scenes, backlight, glass, stairs, low obstacles, moving people and occlusion. Monocular relative depth does not establish metric distance or traversability; 2D object boxes do not establish a clear route. Do not turn a green-marker demo into “safe path” by renaming its output.

## Thinking Machines Tinker

Official docs: [Using Inkling](https://tinker-docs.thinkingmachines.ai/cookbook/inkling/), [models](https://tinker-docs.thinkingmachines.ai/tinker/models/), [Tinker overview](https://tinker-docs.thinkingmachines.ai/). The cookbook documents image inputs, audio support for Inkling/Inkling-Small and shows `thinkingmachines/Inkling-2-Small`. Model-list naming is not perfectly aligned; verify the actual model accessible to the team's credentials at integration time.

`SceneVoiceAdapter` and `TinkerPending` are local boundaries only. No Tinker model is called yet. Before implementing:

1. Obtain actual authorized account credentials in an ignored local environment file and query official server capabilities using the supported SDK.
2. Follow the official current `tml-renderers` examples for image/audio packing; do not assume the FastAPI raw audio container is directly accepted by the model API.
3. Build a small consented dataset of actual images/questions with clock-face labels and explicit unknown cases. Split by scene, not nearly identical consecutive frames.
4. Fine-tune/evaluate short responses, hallucination/unknown rate and measured timing. Retain baseline model and tuned checkpoints, training logs, costs and a held-out comparison.
5. Implement the adapter only after an authenticated sampling call works. Keep semantic answers off the time-critical motor loop; reject unsupported metric distances.

There is no trained Tinker model yet.

## Entrinsik Informer

Official [webhook docs](https://docs.entrinsik.com/developer/guides/magic-apps/webhooks/) describe app-owned handlers, POST to deployed `/_hook/` routes and a signed `token` in the URL. `InformerWebhook` accepts the **exact deployed signed HTTPS URL**, validates its shape and POSTs a typed event. It does not invent an app ID/path or deploy a server. Redirects are disabled; exceptions omit the signed URL.

`HazardEvent` defaults to `simulated:true`, `source:"operator_demo"`, and null coordinates. Baseline camera cards do not create real civic hazards. Before wiring automatic events, implement and verify a real app handler and schema against the tenant, protect credentials, establish consent for images/location, and distinguish operator-confirmed reports from model suggestions. Use idempotent event IDs, rate limits, a retry/outbox process and deduplication in a later revision. This base sender intentionally has no automatic retry that could duplicate reports.

Nothing sends to Informer unless a developer explicitly constructs and invokes the adapter. No sponsor token belongs in the browser or archive. No actual hazard map, GPS report, facilities notification, weekly agent, ADA-compliance determination, or work order was deployed by this task.
