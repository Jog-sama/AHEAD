import pytest

from backend.config import Settings
from tests.conftest import KEY


@pytest.mark.parametrize(
    "values",
    [
        {"api_key": "short"},
        {"device": "other"},
        {"center": 80},
        {"left": 0},
        {"right": 180},
        {"left": 100},
        {"device": "esp32"},
    ],
)
def test_unsafe_settings(values):
    with pytest.raises(ValueError):
        Settings(**({"api_key": KEY} | values))


def test_reverse_mount():
    assert Settings(api_key=KEY, left=100, right=80).left == 100
