from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from backend.config import Settings

KEY = "test-only-backend-key-000000000000"
DEVICE_KEY = "test-only-device-key-000000000000"


@pytest.fixture
def settings():
    return Settings(api_key=KEY)


def frame(lane=None, red=False, ambiguous=False):
    im = np.full((480, 640, 3), 100, np.uint8)
    if lane:
        index = {"left": 0, "center": 1, "right": 2}[lane]
        start = index * 213 + 40
        im[200:400, start : start + 130] = (0, 220, 0)
        if red:
            im[300:450, start : start + 130] = (240, 0, 0)
        if ambiguous:
            start2 = ((index + 1) % 3) * 213 + 40
            im[200:400, start2 : start2 + 130] = (0, 220, 0)
    out = BytesIO()
    Image.fromarray(im).save(out, format="JPEG", quality=85)
    return out.getvalue()
