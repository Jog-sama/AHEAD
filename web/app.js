"use strict";
const $ = id => document.getElementById(id);
let apiKey = "", state = null, cameraStream = null, frameBusy = false;
let sequence = 0, frameTimer = null, manualTimer = null, manualBusy = false;
let recorder = null, recordingStream = null, recordingWanted = false, recordingPending = false;
let recordingTimer = null, audioURL = null, lastCue = "Hold position.";
const canvas = document.createElement("canvas");

function error(message) { $("error").textContent = message || ""; }
async function api(path, body, type = "application/json", method = "POST", timeout = 2000) {
  const response = await fetch(path, {method, headers:{"X-API-Key":apiKey,"Content-Type":type},
    body:method === "GET" ? undefined : type === "application/json" ? JSON.stringify(body || {}) : body,
    signal:AbortSignal.timeout(timeout), cache:"no-store"});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data;
}
function render(next) {
  // Ignore any response from a generation preceding the last observed Stop/Arm.
  if (state && next.generation < state.generation) return;
  state = next;
  $("connection").textContent = next.device === "mock" ? "MOCK DEVICE" : "ESP32 mode";
  $("modeLabel").textContent = `${next.armed ? "ARMED" : "DISARMED"} / ${next.mode.toUpperCase()}`;
  $("phrase").textContent = next.phrase;
  lastCue = next.phrase;
  $("telemetry").textContent = `Last command ${next.commanded_angle}° · ACK age ${next.ack_age_ms ?? "—"} ms · Device HTTP ${next.device_http_ms ?? "—"} ms`;
  if (!next.armed) clearInterval(manualTimer);
  if (next.error) error(next.error);
  const scene = next.vision?.scene;
  $("scene").textContent = scene ? JSON.stringify({reason:next.vision.reason,
    objects:scene.objects?.map(o=>`${o.label} (${Math.round(o.confidence*100)}%)`),
    free_space:scene.free_space, blocked:scene.blocked, confidence:scene.confidence,
    depth:scene.depth_kind, warning:scene.warning, model_error:scene.model_error},null,2) : "No scene evidence yet.";
  if (next.perception?.engine === "observation_only") $("engine").textContent = "Models unavailable: obstacle mode stays neutral. Prepare models and restart.";
  else if (next.perception) $("engine").textContent = "YOLO + relative depth loaded. Experimental floor estimates.";
}
async function stop() {
  clearInterval(manualTimer); clearTimeout(frameTimer);
  if (state) state = {...state, armed:false};
  try { render(await api("/api/stop")); }
  catch (e) { error(`${e.message}. Neutral is NOT confirmed. Remove servo power if necessary.`); }
}
function speak(text) {
  if (!("speechSynthesis" in window)) { error("Speech output unavailable; read the displayed cue."); return; }
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text); utterance.lang = "en-US";
  speechSynthesis.speak(utterance);
}
$("connect").onclick = async () => {
  apiKey = $("key").value.trim(); error("");
  try { render(await api("/api/status", null, "application/json", "GET")); }
  catch (e) { error(e.message); }
};
$("camera").onclick = async () => {
  try {
    if (!window.isSecureContext || !navigator.mediaDevices) throw new Error("Camera needs trusted HTTPS on iPhone. Follow docs/SETUP_MAC.md.");
    if (cameraStream) return;
    cameraStream = await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:"environment"},width:{ideal:640},height:{ideal:480}}});
    $("video").srcObject = cameraStream; await $("video").play();
    const stage = document.querySelector(".stage"); stage.style.height = "auto";
    stage.style.aspectRatio = `${$("video").videoWidth} / ${$("video").videoHeight}`;
    $("cameraLabel").textContent = "Camera ready · target: at most 5 FPS";
    cameraStream.getVideoTracks()[0].addEventListener("ended", () => { stop(); cameraStream = null; });
    error("");
    if ($("autoArm").checked && apiKey && $("mode").value !== "manual") await $("arm").onclick();
  } catch (e) { error(e.message); }
};
$("endCamera").onclick = () => {
  stop(); if (cameraStream) cameraStream.getTracks().forEach(t => t.stop());
  cameraStream = null; $("video").srcObject = null; $("cameraLabel").textContent = "Camera off";
};
$("mode").onchange = () => { if (apiKey) stop(); };
$("arm").onclick = async () => {
  try {
    if (["cv", "obstacle"].includes($("mode").value) && !cameraStream) throw new Error("Start camera before arming OpenCV.");
    clearTimeout(frameTimer); clearInterval(manualTimer); error("");
    render(await api("/api/arm",{mode:$("mode").value})); sequence = 0;
    if (["cv", "obstacle"].includes(state.mode)) sendFrame();
  } catch(e) { error(e.message); }
};
$("stop").onclick = stop;
async function sendFrame() {
  if (frameBusy || !cameraStream || !state?.armed || !["cv", "obstacle"].includes(state.mode)) return;
  frameBusy = true;
  const generation = state.generation, started = performance.now(), video = $("video");
  try {
    if (!video.videoWidth) throw new Error("Camera is not producing frames");
    const scale = Math.min(640/video.videoWidth, 480/video.videoHeight, 1);
    canvas.width = Math.round(video.videoWidth*scale); canvas.height = Math.round(video.videoHeight*scale);
    canvas.getContext("2d").drawImage(video,0,0,canvas.width,canvas.height);
    const blob = await new Promise(resolve => canvas.toBlob(resolve,"image/jpeg",0.7));
    if (!blob) throw new Error("Could not encode camera frame");
    // Prevent a stopped generation from submitting after asynchronous JPEG encoding.
    if (!state?.armed || state.generation !== generation) return;
    const result = await api(`/api/frame?generation=${generation}&sequence=${sequence++}`,blob,"image/jpeg");
    render(result);
    $("cameraLabel").textContent = `Frame round trip ${Math.round(performance.now()-started)} ms · Python ${result.backend_ms} ms`;
  } catch(e) { error(e.message); await stop(); }
  finally {
    frameBusy = false;
    if (state?.armed && ["cv", "obstacle"].includes(state.mode)) frameTimer = setTimeout(sendFrame,Math.max(0,200-(performance.now()-started)));
  }
}
async function manual(direction) {
  if (manualBusy) return;
  if (!state?.armed || state.mode !== "manual") { error("Arm manual mode first, then hold a direction."); return; }
  manualBusy = true;
  try { render(await api("/api/steer",{direction,generation:state.generation})); }
  catch(e) { error(e.message); await stop(); }
  finally { manualBusy = false; }
}
document.querySelectorAll("[data-direction]").forEach(button => {
  const begin = () => { clearInterval(manualTimer); manual(button.dataset.direction); manualTimer = setInterval(() => manual(button.dataset.direction),250); };
  button.onpointerdown = e => { e.preventDefault(); button.setPointerCapture(e.pointerId); begin(); };
  button.onpointerup = button.onpointercancel = () => stop();
  button.onkeydown = e => { if ([" ","Enter"].includes(e.key) && !e.repeat) { e.preventDefault(); begin(); } };
  button.onkeyup = e => { if ([" ","Enter"].includes(e.key)) stop(); };
});
$("ask").onclick = async () => {
  try { const r = await api("/api/voice",{text:$("question").value}); lastCue=r.phrase; $("voiceReply").textContent=r.phrase; speak(r.phrase); }
  catch(e) { error(e.message); }
};
$("speak").onclick = () => speak(lastCue);
$("statusVoice").onclick = async () => {
  try { const r = await api("/api/voice",{text:"status"}); lastCue=r.phrase; $("voiceReply").textContent=r.phrase; speak(r.phrase); }
  catch(e) { error(e.message); }
};
async function recordStart() {
  if (recordingPending || recorder?.state === "recording") return;
  recordingWanted = true; recordingPending = true;
  try {
    if (!isSecureContext || !navigator.mediaDevices || !window.MediaRecorder) throw new Error("Recording needs supported Safari and trusted HTTPS.");
    recordingStream = await navigator.mediaDevices.getUserMedia({audio:true,video:false});
    if (!recordingWanted) { recordingStream.getTracks().forEach(t=>t.stop()); return; }
    const mime = ["audio/mp4","audio/webm;codecs=opus","audio/webm","audio/ogg"].find(x=>MediaRecorder.isTypeSupported(x));
    recorder = new MediaRecorder(recordingStream,mime ? {mimeType:mime} : undefined);
    const chunks = []; const activeRecorder = recorder;
    recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = async () => {
      recordingStream?.getTracks().forEach(t=>t.stop());
      const blob = new Blob(chunks,{type:activeRecorder.mimeType || mime || "audio/mp4"});
      if (audioURL) URL.revokeObjectURL(audioURL);
      audioURL = URL.createObjectURL(blob); $("playback").src=audioURL;
      $("record").textContent="Hold to record · max 4 seconds";
      try {
        const r = await api("/api/audio",blob,blob.type,"POST",30000);
        $("audioStatus").textContent = `${r.received_bytes} bytes received · ${r.transcription || "No transcription"} · not stored`;
        if (r.transcription) $("question").value=r.transcription;
        lastCue=r.phrase; $("voiceReply").textContent=r.phrase;
        // Separate user-tap Speak control remains available if Safari blocks async speech.
        speak(r.phrase);
      } catch(e) { error(e.message); }
    };
    recorder.start(); $("record").textContent="Recording… release to send";
    recordingTimer=setTimeout(recordStop,4000);
  } catch(e) { recordingStream?.getTracks().forEach(t=>t.stop()); error(e.message); }
  finally { recordingPending=false; }
}
function recordStop() {
  recordingWanted=false; clearTimeout(recordingTimer);
  if (recorder?.state === "recording") recorder.stop();
}
$("record").onpointerdown=e=>{e.preventDefault();$("record").setPointerCapture(e.pointerId);recordStart();};
$("record").onpointerup=$("record").onpointercancel=recordStop;
$("record").onkeydown=e=>{if ([" ","Enter"].includes(e.key)&&!e.repeat){e.preventDefault();recordStart();}};
$("record").onkeyup=e=>{if ([" ","Enter"].includes(e.key))recordStop();};
document.addEventListener("visibilitychange",()=>{if(document.hidden){recordStop();if(apiKey)stop();}});
window.addEventListener("pagehide",()=>{recordStop();if(apiKey){fetch("/api/stop",{method:"POST",headers:{"X-API-Key":apiKey},keepalive:true}).catch(()=>{});}});
setInterval(async()=>{if(apiKey && !document.hidden){try{render(await api("/api/status",null,"application/json","GET"));}catch(e){error(e.message);}}},1000);

$("location").onclick = () => {
  if (!navigator.geolocation) { error("Location unavailable."); return; }
  navigator.geolocation.getCurrentPosition(async pos => {
    try { await api("/api/location",{latitude:pos.coords.latitude,longitude:pos.coords.longitude,accuracy:pos.coords.accuracy});
      $("hazardStatus").textContent="Location attached to candidates for 60 seconds.";
    } catch(e) { error(e.message); }
  }, e=>error(e.message), {maximumAge:0,timeout:10000});
};
$("clearLocation").onclick = async () => {
  try { await api("/api/location",null,"application/json","DELETE"); $("hazardStatus").textContent="Location cleared for future events."; }
  catch(e) { error(e.message); }
};
$("hazards").onclick = async () => {
  try { const r=await api("/api/hazards",null,"application/json","GET");
    $("hazardStatus").textContent=`${r.events.length} recent candidates · export ${r.export_enabled ? "enabled" : "off"}`;
    $("hazardList").textContent=r.events.map(e=>`${e.observed_at} | ${e.simulated?"SIMULATED":"REVIEW"} | ${e.label} | ${e.delivered?"delivered":"local/pending"} | ${e.latitude??"no GPS"}, ${e.longitude??""}`).join("\n") || "No hazard candidates recorded.";
  } catch(e) { error(e.message); }
};

$("askTinker").onclick=async()=>{try{const r=await api("/api/voice/tinker",{text:$("question").value},"application/json","POST",10000);$("voiceReply").textContent=`${r.phrase} (${r.source})`;lastCue=r.phrase;speak(r.phrase);}catch(e){error(e.message);}};
