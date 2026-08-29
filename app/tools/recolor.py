"""recolor — single free-text "which part" + a color, one templated
prompt, one fal-ai/flux-2/edit call, always exactly one image out.
Fourth tool alongside on_model_shots.py, catalog_photoshoot.py,
creative_photoshoot.py — real port of the verified-against-real-
fal.ai-calls recolor_flow.py.

Fully self-contained config (own tool_config row, feature_type="recolor"):
recolor_generation (fal-ai/flux-2/edit — its own model, not shared with
any other tool), prompt_writer (only used when "which part" is left
blank), safety_check — plus its own copies of the target-writer and
safety-check system prompts. Same pattern as creative_photoshoot.py.

Still reuses catalog_photoshoot.py's already-debugged CODE directly
(run_safety_check, _vlm_json_call) — only the config values are
duplicated, not the logic — EXCEPT for image assembly and resolution/size
handling, which are genuinely different for this model (max 4 images not
10; a hard 512-2048px per-axis limit, reject rather than auto-scale) and
are NOT reused from catalog_photoshoot, per recolor_flow.py's own
docstring.
"""

import io
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from app.core.fal_provider import FalImageEditProvider
from app.core.tool_config import load_tool_config
from app.tools import catalog_photoshoot as catalog_tool
from app.tools.registry import ToolSpec, register

_CONFIG_PATH = Path(__file__).parent / "recolor_config.json"


def get_config(db: Session) -> dict:
    return load_tool_config(db, "recolor", _CONFIG_PATH)


# =============================================================================
# 1. Reference images — up to 4, first one is always "the photo being edited"
# =============================================================================

RECOLOR_MAX_IMAGES = 4  # confirmed: flux-2/edit silently uses only the first 4 if more are sent


def assemble_recolor_images(urls: list[str]) -> tuple[list[str], list[str]]:
    """Enforces the real 4-image limit ourselves rather than relying on fal
    silently dropping the rest — same principle as every other tool's
    image-count reject, different number because this is a different
    model. urls[0] is always the photo being recolored (already a hosted
    Asset URL by the time this is called — see recolor_controller.py);
    any additional urls are optional references (e.g. a color-swatch
    image)."""
    if len(urls) > RECOLOR_MAX_IMAGES:
        raise ValueError(
            f"{len(urls)} images exceeds flux-2/edit's {RECOLOR_MAX_IMAGES}-image limit — "
            f"trim {len(urls) - RECOLOR_MAX_IMAGES} image(s) and try again."
        )
    labels = ["Image 1 = the photo being edited (preserve everything except the requested change)"]
    labels += [f"Image {i+2} = additional reference (e.g. color/style reference only)" for i in range(len(urls) - 1)]
    return urls, labels


# =============================================================================
# 2. Output settings — aspect ratio / resolution
# =============================================================================

ASPECT_RATIO_MAP = {
    "1:1": "square_hd",
    "3:4": "portrait_4_3",
    "9:16": "portrait_16_9",
    "4:3": "landscape_4_3",
    "16:9": "landscape_16_9",
}
RECOLOR_MIN_DIM = 512
RECOLOR_MAX_DIM = 2048


def build_image_size(resolution_mode: str = "standard", aspect_ratio: str = "1:1", custom_width: int | None = None, custom_height: int | None = None):
    """Different constraint shape from every other tool's build_image_size:
    a hard 512-2048px-per-axis rule — flux-2/edit REJECTS an out-of-range
    custom size rather than auto-scaling (unlike catalog's v5-lite) or
    accepting a wider range (unlike on-model-shots' v4.5). Does not handle
    'match_input' — that's resolved to a concrete 'custom' size via
    compute_matching_size() by the caller before this is used."""
    if resolution_mode == "standard":
        if aspect_ratio not in ASPECT_RATIO_MAP:
            raise ValueError(f"Unknown aspect_ratio {aspect_ratio!r} — one of {list(ASPECT_RATIO_MAP)}")
        return ASPECT_RATIO_MAP[aspect_ratio]
    if resolution_mode == "custom":
        if custom_width is None or custom_height is None:
            raise ValueError("resolution_mode='custom' requires custom_width and custom_height")
        if not (RECOLOR_MIN_DIM <= custom_width <= RECOLOR_MAX_DIM and RECOLOR_MIN_DIM <= custom_height <= RECOLOR_MAX_DIM):
            raise ValueError(
                f"{custom_width}x{custom_height} invalid — each side must be "
                f"{RECOLOR_MIN_DIM}-{RECOLOR_MAX_DIM}px for this model."
            )
        return {"width": custom_width, "height": custom_height}
    raise ValueError(f"Unknown resolution_mode: {resolution_mode!r} — one of 'standard', 'custom'")


def compute_matching_size(image_bytes: bytes) -> dict:
    """Default behavior: no explicit aspect-ratio/quality choice means
    "don't change the photo's own proportions" — reads the photo's real
    width/height and scales them (preserving aspect ratio) to fit this
    model's 512-2048 per-axis range, rather than silently forcing a fixed
    ratio onto every input. Takes bytes (not a file path, unlike
    recolor_flow.py's version) since the backend's "photo being edited" is
    an already-uploaded Asset, fetched over HTTP by the caller, not a
    local file."""
    with Image.open(io.BytesIO(image_bytes)) as img:
        width, height = img.size

    scale = 1.0
    if max(width, height) > RECOLOR_MAX_DIM:
        scale = RECOLOR_MAX_DIM / max(width, height)
    elif min(width, height) < RECOLOR_MIN_DIM:
        scale = RECOLOR_MIN_DIM / min(width, height)

    new_width = max(RECOLOR_MIN_DIM, min(RECOLOR_MAX_DIM, round(width * scale)))
    new_height = max(RECOLOR_MIN_DIM, min(RECOLOR_MAX_DIM, round(height * scale)))
    return {"width": new_width, "height": new_height}


# =============================================================================
# 3. Prompt composition — no LLM call for the template itself; one
# conditional LLM call only when "which part" is left blank
# =============================================================================

def suggest_recolor_target(config: dict, image_urls: list[str]) -> str:
    """Node: user gave no description -> one LLM+Vision call looks at
    Image 1 and picks a short target phrase. That phrase then goes
    through the exact same build_recolor_prompt() template a
    manually-typed description would — this function only ever decides
    WHAT the description is, never composes the final prompt itself."""
    result = catalog_tool._vlm_json_call(
        model=config["models"]["prompt_writer"], system=config["prompts"]["recolor_target_writer"],
        prompt='Identify the recolorable subject in Image 1. Return ONLY a JSON object: {"target": "<short noun phrase>"}.',
        image_urls=image_urls[:1], max_tokens=50,
    )
    return result["target"]


def build_recolor_prompt(config: dict, description: str, color: str) -> str:
    """description: one free-text field — "which part should be
    recolored", the user's whole request in their own words — always
    non-empty by the time this is called (a blank one is filled in via
    suggest_recolor_target() by the caller first). color: a hex code
    (e.g. "#FF0000") or a plain color name — either works per fal's own
    docs."""
    return (
        f"{config['prompts']['preservation_instructions']}\n\nUser request:\n"
        f"Change {description} in #Image_1 to {color}. Keep everything else unchanged."
    )


# =============================================================================
# 4. Tool registration — its own FalImageEditProvider instance (own model,
# own config row). flux-2/edit's schema has no max_images field (confirmed
# 2026-08-29), unlike the Seedream-based tools — include_max_images=False.
# =============================================================================

provider = FalImageEditProvider(feature_type="recolor", model_config_key="recolor_generation", include_max_images=False)

register(
    ToolSpec(
        feature_type="recolor",
        display_name="Recolor",
        output_media_type="image",
        provider=provider,
    )
)
