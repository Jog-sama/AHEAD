from io import BytesIO

import pytest
from PIL import Image

from backend.vision import MarkerVision, decode_frame
from tests.conftest import frame


@pytest.mark.parametrize("lane", ["left", "center", "right"])
def test_lanes(lane):
    assert MarkerVision().predict(frame(lane)).direction == lane


@pytest.mark.parametrize("data", [frame(), frame("left", red=True), frame("left", ambiguous=True)])
def test_unknown(data):
    assert MarkerVision().predict(data).direction == "unknown"


@pytest.mark.parametrize("data", [b"", b"garbage", b"x" * 400001])
def test_bad_jpeg(data):
    with pytest.raises(ValueError):
        decode_frame(data)


def test_dimension_bomb_and_format():
    for size, fmt in [((1281, 100), "JPEG"), ((100, 100), "PNG")]:
        buf = BytesIO()
        Image.new("RGB", size).save(buf, format=fmt)
        with pytest.raises(ValueError):
            decode_frame(buf.getvalue())
