"""Optional sponsor boundaries. No endpoint or credential is inferred."""

import hashlib
import hmac
from typing import Protocol
from urllib.parse import parse_qs, urlparse

import httpx
from pydantic import BaseModel, Field


class SceneAnswer(BaseModel):
    phrase: str = Field(max_length=80)
    direction: str
    source: str


class SceneVoiceAdapter(Protocol):
    async def describe(self, jpeg: bytes, audio: bytes | None, question: str) -> SceneAnswer: ...


class TinkerPending:
    async def describe(self, jpeg: bytes, audio: bytes | None, question: str) -> SceneAnswer:
        raise NotImplementedError(
            "Verify Tinker model access, renderer, training and sampling first"
        )


class HazardEvent(BaseModel):
    schema_version: int = 1
    event_id: str
    observed_at: str
    label: str = Field(max_length=120)
    source: str = "operator_demo"
    simulated: bool = True
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    severity: str = "review"
    confidence: float = Field(default=0, ge=0, le=1)
    reason: str = Field(default="", max_length=300)
    direction: str = "unknown"


class InformerWebhook:
    """Explicit use only. URL must be issued by real Informer deployment; not in CV loop."""

    def __init__(self, deployed_signed_url: str, shared_secret: str):
        url = urlparse(deployed_signed_url)
        if (
            url.scheme != "https"
            or not url.hostname
            or "/_hook/" not in url.path
            or not parse_qs(url.query).get("token")
            or url.username
            or url.fragment
        ):
            raise ValueError("Supply the exact HTTPS signed webhook URL issued by Informer")
        if len(shared_secret) < 32:
            raise ValueError("Set a 32+ character Informer webhook secret")
        self._url = deployed_signed_url
        self._secret = shared_secret.encode()

    async def send(self, event: HazardEvent) -> bool:
        try:
            payload = event.model_dump_json().encode()
            signature = hmac.new(self._secret, payload, hashlib.sha256).hexdigest()
            async with httpx.AsyncClient(
                timeout=5, follow_redirects=False, trust_env=False
            ) as client:
                result = await client.post(
                    self._url,
                    content=payload,
                    headers={
                        "content-type": "application/json",
                        "x-ahead-signature": signature,
                    },
                )
                result.raise_for_status()
                return True
        except httpx.HTTPError:
            raise RuntimeError("Informer delivery failed; verify handler and credentials") from None
