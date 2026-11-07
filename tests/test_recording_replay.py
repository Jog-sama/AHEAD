"""Regression tests for recorded portrait frames and full-duration offline replay."""
import json
import sys

import cv2
import numpy as np
import pytest

from backend.obstacles import ObstacleVision


class RecordingModels:
    def __init__(self):
        self.seen_shape = None

    def infer(self, image):
        self.seen_shape = image.shape[:2]
        h, w = self.seen_shape
        return [], np.repeat(np.linspace(0, 1, h)[:, None], w, axis=1).astype(np.float32)


@pytest.mark.parametrize(
    ("original_hw", "expected_hw"),
    [
        ((480, 640), (240, 320)),
        ((640, 480), (320, 240)),
        ((640, 360), (320, 180)),
        ((360, 640), (180, 320)),
    ],
)
def test_obstacle_model_keeps_camera_aspect_ratio(original_hw, expected_hw):
    rng = np.random.default_rng(5)
    frame = rng.integers(50, 205, (*original_hw, 3), dtype=np.uint8)
    ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    assert ok and len(jpeg) < 400_000
    models = RecordingModels()
    ObstacleVision(models).predict(jpeg.tobytes())
    assert models.seen_shape == expected_hw


def test_replay_samples_beginning_middle_and_end(tmp_path, monkeypatch):
    import scripts.replay_perception as replay
    from backend.vision import Decision

    video = tmp_path / "camera.mp4"
    writer = cv2.VideoWriter(
        str(video), cv2.VideoWriter_fourcc(*"mp4v"), 5, (320, 240)
    )
    if not writer.isOpened():
        pytest.skip("OpenCV MP4 encoder unavailable")
    for i in range(10):
        writer.write(np.full((240, 320, 3), i * 20, dtype=np.uint8))
    writer.release()

    class OfflineVision:
        def __init__(self, *args, **kwargs):
            pass

        def predict(self, jpeg):
            return Decision("unknown", "Hold position.", "Mock replay", source="test")

    monkeypatch.setattr(replay, "NeuralModels", lambda *a, **kw: object())
    monkeypatch.setattr(replay, "ObstacleVision", OfflineVision)
    out = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", ["replay", str(video), "--frames", "3",
                                     "--output", str(out)])
    replay.main()
    report = json.loads(out.read_text())
    assert report["sampling"] == "full_video_evenly_spaced"
    assert report["hardware_tested"] is False
    assert [x["source_frame"] for x in report["frames"]] == [0, 4, 9]
    assert report["frames"][-1]["time_s"] == pytest.approx(1.8)
