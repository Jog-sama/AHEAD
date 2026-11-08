"""Optional native Tinker image + text sampling. No actuator access.

The phone audio path uses local Whisper first. This is explicitly not native
audio fine-tuning. Only grounded candidate phrases are accepted for speech.
"""

import asyncio
import base64
import os

from .spatial_voice import grounded_candidates, local_answer


def messages_for(jpeg, question, allowed=None):
    instruction = (
        "Describe visible objects with clock positions in at most eight words. "
        "Never give distances or walking instructions. If unsure say "
        "'Scene uncertain. Hold position.'"
    )
    if allowed:
        instruction += " Return exactly one of these grounded phrases: " + repr(allowed)
    return [
        {"role": "system", "content": instruction},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
                    },
                },
            ],
        },
    ]


class TinkerVoice:
    def __init__(self):
        self.model = os.getenv("TV_TINKER_MODEL", "thinkingmachines/Inkling-2-Small")
        self.checkpoint = os.getenv("TV_TINKER_CHECKPOINT")
        self.allow_base = os.getenv("TV_TINKER_ALLOW_BASE") == "1"
        self.client = self.renderer = None
        self.sdk = None
        self.lock = asyncio.Lock()

    def load_runtime(self):
        import tinker
        from tinker_cookbook import model_info
        from tinker_cookbook.renderers import get_renderer
        from tinker_cookbook.tokenizer_utils import get_tokenizer

        renderer = get_renderer(
            model_info.get_recommended_renderer_name(self.model), get_tokenizer(self.model)
        )
        return tinker, renderer, tinker.ServiceClient()

    async def setup(self):
        if not self.checkpoint and not self.allow_base:
            raise RuntimeError("Configure a trained TV_TINKER_CHECKPOINT")
        self.sdk, self.renderer, service = await asyncio.to_thread(self.load_runtime)
        self.client = await service.create_sampling_client(
            **({"model_path": self.checkpoint} if self.checkpoint else {"base_model": self.model})
        )

    async def describe(self, jpeg, question, decision, cue):
        if self.lock.locked():
            return {"phrase": "Voice busy. Try again.", "source": "local_guard"}
        async with self.lock:
            if self.client is None:
                await self.setup()
            grounded = local_answer(question, decision, cue)["phrase"]
            allowed = grounded_candidates(question, decision, cue)
            if "Scene uncertain. Hold position." not in allowed:
                allowed.append("Scene uncertain. Hold position.")
            prompt = await asyncio.to_thread(
                self.renderer.build_generation_prompt, messages_for(jpeg, question, allowed)
            )
            response = await self.client.sample(
                prompt=prompt,
                num_samples=1,
                sampling_params=self.sdk.SamplingParams(
                    max_tokens=80, temperature=0, stop=self.renderer.get_stop_sequences()
                ),
            )
            message, _ = self.renderer.parse_response(response.sequences[0].tokens)
            phrase = (
                message.get("content")
                if isinstance(message, dict)
                else getattr(message, "content", None)
            )
            if not isinstance(phrase, str) and isinstance(phrase, list):
                phrase = "".join(
                    p.get("text", "") if isinstance(p, dict) else getattr(p, "text", "")
                    for p in phrase
                )
            if not isinstance(phrase, str) or phrase.strip() not in allowed:
                return {
                    "phrase": grounded,
                    "source": "local_guard",
                    "detail": "Ungrounded model output rejected",
                }
            return {
                "phrase": phrase.strip(),
                "source": "tinker",
                "checkpoint_configured": bool(self.checkpoint),
                "direction": "unknown",
            }
