"""FalImageEditProvider — generic async submit/poll AIProvider (see
app/core/ai_provider.py) against fal.ai's queue API, for any tool that
edits/generates ONE image from a prompt + a list of input image URLs.
Knows nothing about poses, shots, prompts, or safety — those live in each
tool's own file (app/tools/on_model_shots.py, app/tools/catalog_photoshoot.py),
which builds input_payload and hands it to a configured instance of this
class. Two tools, two instances, each pointed at a different tool_config
row/key — see
docs/superpowers/specs/2026-08-29-catalog-photoshoot-tool-design.md.

Uses fal's real async submit()/status()/result() calls, not the blocking
.subscribe() the original flow.py/catalog_flow.py scripts use — submit()
here returns as soon as fal hands back a request id, poll_result() checks
status once per call, same non-blocking shape as MockAIProvider."""

from pathlib import Path

import fal_client
import httpx

from app.core.ai_provider import AIProvider, GenerationFailed, GenerationHandle, GenerationPending, GenerationResult
from app.core.db import SessionLocal
from app.core.tool_config import load_tool_config

_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _guess_extension(url: str, content_type: str) -> str:
    filename = url.rsplit("/", 1)[-1]
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix in ("jpg", "jpeg", "png", "webp", "gif"):
        return "jpg" if suffix == "jpeg" else suffix
    return _EXTENSION_BY_CONTENT_TYPE.get(content_type.split(";")[0].strip().lower(), "jpg")


class FalImageEditProvider(AIProvider):
    def __init__(self, feature_type: str, model_config_key: str, include_max_images: bool = True):
        self.feature_type = feature_type
        self.model_config_key = model_config_key
        self.include_max_images = include_max_images  # False for models whose
        # schema doesn't have this field (e.g. fal-ai/flux-2/edit, confirmed
        # 2026-08-29 — recolor_flow.py's verified request omits it) — sending
        # an unrecognized field to a model that doesn't expect it isn't
        # assumed safe, so this is opt-out per provider instance, not global.
        self._fallback_path = Path(__file__).resolve().parent.parent / "tools" / f"{feature_type}_config.json"

    def _model_id(self) -> str:
        db = SessionLocal()
        try:
            config = load_tool_config(db, self.feature_type, self._fallback_path)
        finally:
            db.close()
        return config["models"][self.model_config_key]

    def submit(self, feature_type, source_asset_url, input_payload):
        model = self._model_id()
        args = {
            "prompt": input_payload["prompt"],
            "image_urls": input_payload["image_urls"],
            "image_size": input_payload["image_size"],
            "num_images": 1,
            "enable_safety_checker": True,  # second, independent safety layer — do not disable
        }
        if self.include_max_images:
            args["max_images"] = 1
        handle = fal_client.submit(model, arguments=args)
        return GenerationHandle(external_job_id=f"{model}::{handle.request_id}", provider="fal")

    def poll_result(self, handle: GenerationHandle) -> GenerationResult:
        model, request_id = handle.external_job_id.split("::", 1)
        current_status = fal_client.status(model, request_id, with_logs=False)

        if isinstance(current_status, fal_client.Completed):
            if current_status.error:
                raise GenerationFailed(current_status.error)
            result = fal_client.result(model, request_id)
            image = result["images"][0]
            resp = httpx.get(image["url"], timeout=60.0)
            resp.raise_for_status()
            extension = _guess_extension(image["url"], resp.headers.get("content-type", ""))
            return GenerationResult(media_type="image", content=resp.content, extension=extension)

        if isinstance(current_status, (fal_client.InProgress, fal_client.Queued)):
            raise GenerationPending()

        raise GenerationFailed(f"Unexpected fal status: {current_status!r}")
