"""The AI side of a generation job. One small interface, one mock
implementation for now — real per-tool logic (23 tools, keyed off
feature_type) plugs in later by swapping the line at the bottom for a real
provider. Nothing about the job/asset plumbing (app/worker.py,
app/controllers/generation_controller.py) needs to change when that happens.

Shaped around submit-then-poll, not a single blocking call, because that's
how real aggregators (fal.ai, Segmind, ...) actually work: you submit a job
and get an external id back in ~1s, and the real generation (seconds to
minutes, more for video) happens on their side, checked later. A provider
that can only respond synchronously can still implement this interface —
submit() does the whole call and poll_result() just returns the result
immediately — but a provider that can't must not be forced into blocking
one worker slot for its entire generation time, so the interface is built
around the harder (async) case, not the easier one.
"""

import base64
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.core.config import settings


@dataclass
class GenerationHandle:
    """What submit() returns immediately — an external reference to poll
    later, not the result itself. Round-trips through the GenerationJob row
    (external_job_id, provider columns) between arq retries, since the
    retry that eventually polls it to completion may land on a different
    worker process than the one that submitted it."""

    external_job_id: str
    provider: str


@dataclass
class GenerationResult:
    media_type: str  # "image" | "video"
    content: bytes
    extension: str


class GenerationPending(Exception):
    """Raised by poll_result() when the provider's job hasn't finished yet.
    Not an error — app/worker.py catches this and requeues the poll via
    arq's Retry rather than treating it as a failure."""


class GenerationFailed(Exception):
    """Raised by poll_result() when the provider itself reports the job
    failed (as opposed to our own timeout/network errors, which the worker
    handles separately). The message becomes GenerationJob.error."""


class AIProvider(ABC):
    @abstractmethod
    def submit(
        self, feature_type: str, source_asset_url: str | None, input_payload: dict[str, Any]
    ) -> GenerationHandle:
        """Hands the job to the provider and returns immediately. Do the
        minimum HTTP call needed to get an external job id — no polling,
        no waiting, this must return in about as long as one HTTP request
        takes."""
        ...

    @abstractmethod
    def poll_result(self, handle: GenerationHandle) -> GenerationResult:
        """One status check. Raises GenerationPending if still running,
        GenerationFailed if the provider reports failure, otherwise returns
        the finished result. Must also be a single fast HTTP call — never
        loop or sleep inside this method, app/worker.py owns the polling
        cadence (GENERATION_POLL_INTERVAL_SECONDS)."""
        ...


# A real, tiny, valid 1x1 transparent PNG — genuinely openable, so the loop
# this proves (job -> asset -> a URL you can actually fetch) is real, even
# though the "generation" itself is fake.
_FAKE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class MockAIProvider(AIProvider):
    """Simulates a provider that takes MOCK_GENERATION_DELAY_SECONDS to
    finish, without ever blocking a worker — the "ready at" timestamp is
    encoded directly in the external_job_id (there's nowhere else to put
    it: submit() and poll_result() may run in different processes, and a
    real provider's answer would live on their server, not ours). Swap for
    a real provider (dispatching on feature_type) once actual tools exist."""

    def submit(
        self, feature_type: str, source_asset_url: str | None, input_payload: dict[str, Any]
    ) -> GenerationHandle:
        ready_at = time.time() + settings.MOCK_GENERATION_DELAY_SECONDS
        return GenerationHandle(external_job_id=str(ready_at), provider="mock")

    def poll_result(self, handle: GenerationHandle) -> GenerationResult:
        if time.time() < float(handle.external_job_id):
            raise GenerationPending()
        return GenerationResult(media_type="image", content=_FAKE_PNG, extension="png")


# The one line every caller goes through. Swap for a real provider later;
# nothing else in the app changes.
ai_provider: AIProvider = MockAIProvider()
