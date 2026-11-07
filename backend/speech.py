"""Optional local speech input. Not used for actuation; no cloud audio upload."""

from io import BytesIO
from typing import Protocol


class Transcriber(Protocol):
    def transcribe(self, data: bytes) -> str: ...


class LocalWhisper:
    def __init__(self, model_path: str):
        from faster_whisper import WhisperModel

        self.model = WhisperModel(
            model_path,
            device="cpu",
            compute_type="int8",
            cpu_threads=2,
            num_workers=1,
            local_files_only=True,
        )

    def transcribe(self, data: bytes) -> str:
        import av
        import numpy as np

        chunks, count = [], 0
        try:
            with av.open(BytesIO(data)) as container:
                resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
                for frame in container.decode(audio=0):
                    for resampled in resampler.resample(frame):
                        samples = resampled.to_ndarray().reshape(-1)
                        count += len(samples)
                        if count > 8 * 16000:
                            raise ValueError("Audio must be eight seconds or less")
                        chunks.append(samples)
                for resampled in resampler.resample(None):
                    samples = resampled.to_ndarray().reshape(-1)
                    count += len(samples)
                    if count > 8 * 16000:
                        raise ValueError("Audio must be eight seconds or less")
                    chunks.append(samples)
        except Exception as exc:
            raise ValueError("Cannot decode clip; use a short microphone recording") from exc
        if count < 1600:
            raise ValueError("Recording is too short")
        audio = np.concatenate(chunks).astype(np.float32) / 32768.0
        segments, _ = self.model.transcribe(
            audio, language="en", beam_size=1, condition_on_previous_text=False, vad_filter=True
        )
        return " ".join(s.text.strip() for s in segments)[:200].strip()
