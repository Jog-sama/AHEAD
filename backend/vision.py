"""Deliberately constrained CV: green target / red exclusion cards, NOT free-space sensing."""

import warnings
from dataclasses import asdict, dataclass
from io import BytesIO
from typing import Literal, Protocol

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

Direction = Literal["left", "center", "right", "unknown"]


@dataclass(frozen=True)
class Decision:
    direction: Direction
    phrase: str
    reason: str
    scores: tuple[float, float, float] = (0.0, 0.0, 0.0)
    source: str = "opencv_markers"
    scene: dict | None = None

    def json(self) -> dict:
        return asdict(self)


class VisionAdapter(Protocol):
    def predict(self, jpeg: bytes) -> Decision: ...


def phrase_for(direction: Direction) -> str:
    return {
        "left": "Demo target, 10 o'clock.",
        "center": "Demo target, 12 o'clock.",
        "right": "Demo target, 2 o'clock.",
        "unknown": "Uncertain. Hold position.",
    }[direction]


def decode_frame(data: bytes) -> np.ndarray:
    if not data or len(data) > 400_000:
        raise ValueError("JPEG must be 1..400000 bytes")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as im:
                if im.format != "JPEG":
                    raise ValueError("Only JPEG frames are accepted")
                w, h = im.size
                if min(w, h) < 96 or max(w, h) > 1280 or w * h > 1_000_000:
                    raise ValueError(
                        "Use 640x480 or smaller; dimensions must be 96..1280"
                    )
                im.load()
                rgb = np.asarray(im.convert("RGB"))
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as exc:
        raise ValueError("Invalid or oversized JPEG") from exc
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


class MarkerVision:
    def predict(self, jpeg: bytes) -> Decision:
        image = decode_frame(jpeg)
        image = cv2.resize(image, (480, 360))
        hsv = cv2.cvtColor(image[120:340, :], cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (35, 90, 65), (85, 255, 255))
        red = cv2.bitwise_or(
            cv2.inRange(hsv, (0, 110, 65), (10, 255, 255)),
            cv2.inRange(hsv, (170, 110, 65), (179, 255, 255)),
        )
        kernel = np.ones((5, 5), np.uint8)
        green = cv2.morphologyEx(green, cv2.MORPH_OPEN, kernel)
        scores = tuple(
            float(np.mean(green[:, i * 160 : (i + 1) * 160] > 0)) for i in range(3)
        )
        blocked = tuple(
            float(np.mean(red[:, i * 160 : (i + 1) * 160] > 0)) for i in range(3)
        )
        best = int(np.argmax(scores))
        second = sorted(scores)[-2]
        if scores[best] < 0.04:
            reason = "No sufficiently large green demo target"
        elif scores[best] - second < 0.02:
            reason = "Ambiguous target across lanes"
        elif blocked[best] > 0.08:
            reason = "Red exclusion card in target lane"
        else:
            direction: Direction = ("left", "center", "right")[best]
            return Decision(
                direction, phrase_for(direction), "Green demo target", scores
            )
        return Decision("unknown", phrase_for("unknown"), reason, scores)
