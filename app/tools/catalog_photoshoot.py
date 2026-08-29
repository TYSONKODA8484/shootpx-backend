"""catalog_photoshoot — pure product photography: N reference images of one
product in, N distinct catalog shots out. No model-selection step (unlike
on_model_shots) — any person appearing in a shot is incidental to a
composition the VLM chose (e.g. a worn/lifestyle angle), not a chosen
identity. Real implementation ported from the verified-against-real-
fal.ai-calls catalog_flow.py, adapted to read its model ids and system
prompts from DB-or-JSON config (app/core/tool_config.py's
load_tool_config(), this tool's own catalog_photoshoot_config.json)
instead of hardcoding them — see
docs/superpowers/specs/2026-08-29-catalog-photoshoot-tool-design.md.

Standalone on purpose (duplicates a few small helpers with
on_model_shots.py rather than sharing them) — same philosophy the original
catalog_flow.py's docstring states explicitly, so this tool keeps working
even if on_model_shots.py is ever removed.
"""

import json
from pathlib import Path

import fal_client
from sqlalchemy.orm import Session

from app.core.fal_provider import FalImageEditProvider
from app.core.tool_config import load_tool_config
from app.tools.registry import ToolSpec, register

_CONFIG_PATH = Path(__file__).parent / "catalog_photoshoot_config.json"
_VLM_ENDPOINT = "openrouter/router/vision"


def get_config(db: Session) -> dict:
    return load_tool_config(db, "catalog_photoshoot", _CONFIG_PATH)


# =============================================================================
# Shared helpers
# =============================================================================

def to_hosted_url(path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return fal_client.upload_file(path_or_url)


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text


def _extract_json_text(text: str) -> str:
    text = _strip_json_fence(text)
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = text.find(open_ch), text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue
    return text


def _vlm_json_call(model: str, system: str, prompt: str, image_urls: list[str] | None = None, max_tokens: int = 1000) -> dict:
    """`reasoning: True` is mandatory for this tool's configured
    prompt_writer model (gemini-3.1-pro-preview 400s without it, confirmed
    2026-08-29) — sent unconditionally, non-reasoning models just ignore it."""
    args = {
        "model": model,
        "system_prompt": system,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0,
        "reasoning": True,
    }
    if image_urls:
        args["image_urls"] = image_urls
    result = fal_client.subscribe(_VLM_ENDPOINT, arguments=args, with_logs=True)
    return json.loads(_extract_json_text(result["output"]))


# =============================================================================
# Product images
# =============================================================================

def assemble_product_images(product_images: list[str]) -> tuple[list[str], list[str]]:
    if len(product_images) > 10:
        raise ValueError(
            f"{len(product_images)} product images exceeds the 10-image input limit — "
            f"trim {len(product_images) - 10} image(s) and try again."
        )
    image_urls = [to_hosted_url(p) for p in product_images]
    labels = [f"Image {i+1} = product reference (exact product, preserve fidelity)" for i in range(len(image_urls))]
    return image_urls, labels


# =============================================================================
# Output settings — aspect ratio / resolution
# =============================================================================

ASPECT_RATIO_MAP = {
    "1:1": "square_hd",
    "3:4": "portrait_4_3",
    "9:16": "portrait_16_9",
    "4:3": "landscape_4_3",
    "16:9": "landscape_16_9",
}
RESOLUTION_MODES = ["standard", "auto_2K", "auto_3K", "auto_4K", "custom"]
CATALOG_MIN_TOTAL_PX = 2560 * 1440
CATALOG_MAX_TOTAL_PX = 4096 * 4096


def build_image_size(resolution_mode: str = "standard", aspect_ratio: str = "1:1", custom_width: int | None = None, custom_height: int | None = None):
    """Different constraint shape from on_model_shots' build_image_size:
    catalog's endpoint (bytedance/seedream/v5/lite/edit) auto-scales an
    out-of-range custom size rather than rejecting it."""
    if resolution_mode == "standard":
        if aspect_ratio not in ASPECT_RATIO_MAP:
            raise ValueError(f"Unknown aspect_ratio {aspect_ratio!r} — one of {list(ASPECT_RATIO_MAP)}")
        return ASPECT_RATIO_MAP[aspect_ratio]
    if resolution_mode in ("auto_2K", "auto_3K", "auto_4K"):
        return resolution_mode
    if resolution_mode == "custom":
        if custom_width is None or custom_height is None:
            raise ValueError("resolution_mode='custom' requires custom_width and custom_height")
        return {"width": custom_width, "height": custom_height}  # fal auto-scales an
        # out-of-range size to fit rather than rejecting it — no validate-and-raise
        # step here, unlike on_model_shots' Seedream 4.5 edit
    raise ValueError(f"Unknown resolution_mode: {resolution_mode!r} — one of {RESOLUTION_MODES}")


# =============================================================================
# Safety check
# =============================================================================

BLOCKED_TERMS = ["child", "minor", "teen", "kid", "underage"]


def run_safety_check(config: dict, image_urls: list[str], user_prompt: str | None = None) -> tuple[bool, str]:
    if user_prompt:
        text = user_prompt.lower()
        for term in BLOCKED_TERMS:
            if term in text:
                return False, f"blocked term '{term}' in prompt"

    result = _vlm_json_call(
        model=config["models"]["safety_check"], system=config["prompts"]["safety_check"],
        prompt="Classify these images per the rules in the system prompt.",
        image_urls=image_urls, max_tokens=200,
    )
    return bool(result["pass"]), result.get("reason", "")


# =============================================================================
# LLM+Vision — build N shot prompts
# =============================================================================

def _validate_shot_prompts(prompts, num_outputs: int) -> tuple[bool, str]:
    if not isinstance(prompts, list):
        return False, f"expected a JSON array, got {type(prompts).__name__}"
    if len(prompts) != num_outputs:
        return False, f"expected exactly {num_outputs} prompts, got {len(prompts)}"
    if not all(isinstance(p, str) and p.strip() for p in prompts):
        return False, "one or more prompts is empty or not a string"
    if len(set(p.strip() for p in prompts)) != len(prompts):
        return False, "duplicate prompts — the VLM repeated one shot instead of planning N distinct ones"
    return True, ""


def build_shot_prompts(config: dict, image_urls: list[str], labels: list[str], num_outputs: int, user_prompt: str | None = None) -> list[str]:
    prompt_text = (
        "Product reference images, in order:\n" + "\n".join(labels)
        + f"\n\nWrite exactly {num_outputs} distinct catalog-shot prompts for this product."
    )
    if user_prompt:
        prompt_text += (
            f"\n\nUser's additional instructions (creative direction — still preserve exact "
            f"product fidelity and the adult-only rule above): {user_prompt}"
        )
    prompt_text += f" Return ONLY a JSON array of {num_outputs} strings, nothing else."

    last_error = None
    for attempt in range(2):  # one retry
        prompts = _vlm_json_call(
            model=config["models"]["prompt_writer"], system=config["prompts"]["shot_prompt_writer"],
            prompt=prompt_text, image_urls=image_urls, max_tokens=1500,
        )
        ok, reason = _validate_shot_prompts(prompts, num_outputs)
        if ok:
            return prompts
        last_error = reason

    raise ValueError(f"Shot-list planning failed twice: {last_error}")


# =============================================================================
# Tool registration
# =============================================================================

provider = FalImageEditProvider(feature_type="catalog_photoshoot", model_config_key="catalog_generation")

register(
    ToolSpec(
        feature_type="catalog_photoshoot",
        display_name="Catalog Photoshoot",
        output_media_type="image",
        provider=provider,
    )
)
