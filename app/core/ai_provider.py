"""The AI side of a generation job. One small interface, one mock
implementation for now — real per-tool logic (23 tools, keyed off
feature_type) plugs in later by swapping this line for a real provider.
Nothing about the job/asset plumbing needs to change when that happens.
"""

import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class GenerationResult:
    media_type: str  # "image" | "video"
    content: bytes
    extension: str


class AIProvider(ABC):
    @abstractmethod
    def generate(
        self, feature_type: str, source_asset_url: str | None, input_payload: dict[str, Any]
    ) -> GenerationResult: ...


# A real, tiny, valid 1x1 transparent PNG — genuinely openable, so the loop
# this proves (job -> asset -> a URL you can actually fetch) is real, even
# though the "generation" itself is fake.
_FAKE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class MockAIProvider(AIProvider):
    """Returns a fake result instantly. Proves the request -> job -> asset
    loop end to end without a real AI call or any per-tool logic. Swap for
    a real provider (dispatching on feature_type) once actual tools exist."""

    def generate(
        self, feature_type: str, source_asset_url: str | None, input_payload: dict[str, Any]
    ) -> GenerationResult:
        return GenerationResult(media_type="image", content=_FAKE_PNG, extension="png")


# The one line every caller goes through. Swap for a real provider later;
# nothing else in the app changes.
ai_provider: AIProvider = MockAIProvider()
