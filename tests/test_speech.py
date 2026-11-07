from fastapi.testclient import TestClient

from backend.app import create_app
from tests.conftest import KEY


class FakeSpeech:
    def transcribe(self, data: bytes) -> str:
        return "status"


def test_audio_transcription_adapter(settings):
    with TestClient(create_app(settings, transcriber=FakeSpeech())) as c:
        result = c.post(
            "/api/audio",
            content=b"fake-adapter-test-only",
            headers={"X-API-Key": KEY, "Content-Type": "audio/mp4"},
        ).json()
        assert result["transcription"] == "status"
        assert result["phrase"] == "Disarmed. Hold position."
        assert result["stored"] is False
