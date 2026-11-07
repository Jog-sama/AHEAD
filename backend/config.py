import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    device: str = "mock"
    esp32_url: str = "http://192.168.1.123"
    device_token: str = ""
    left: int = 80
    center: int = 90
    right: int = 100
    input_timeout: float = 0.7
    request_timeout: float = 0.35

    def __post_init__(self) -> None:
        if self.device not in {"mock", "esp32"}:
            raise ValueError("TV_DEVICE must be mock or esp32")
        if len(self.api_key) < 24:
            raise ValueError("Set TV_API_KEY (24+ characters); run python scripts/configure.py")
        if self.center != 90 or any(not 75 <= x <= 105 for x in (self.left, self.right)):
            raise ValueError("Center must be 90; left/right must be within 75..105")
        if not (self.left < self.center < self.right or self.right < self.center < self.left):
            raise ValueError("Left and right must lie on opposite sides of neutral")
        if self.device == "esp32":
            parsed = urlparse(self.esp32_url)
            if parsed.scheme != "http" or not parsed.hostname or parsed.path not in {"", "/"}:
                raise ValueError("TV_ESP32_URL must be http://<device-ip>[:port]")
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("Device URL must not contain credentials, query, or fragment")
            if len(self.device_token) < 24:
                raise ValueError("Set TV_DEVICE_TOKEN to match firmware (24+ characters)")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            api_key=os.getenv("TV_API_KEY", ""),
            device=os.getenv("TV_DEVICE", "mock"),
            esp32_url=os.getenv("TV_ESP32_URL", "http://192.168.1.123"),
            device_token=os.getenv("TV_DEVICE_TOKEN", ""),
            left=int(os.getenv("TV_LEFT", "80")),
            center=int(os.getenv("TV_CENTER", "90")),
            right=int(os.getenv("TV_RIGHT", "100")),
        )
