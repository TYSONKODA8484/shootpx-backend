"""on_model_shots — puts an uploaded product/garment shot on a model.

Real implementation (was a MockAIProvider stub) — ported from the
verified-against-real-fal.ai-calls flow.py, adapted to read every model id
and system prompt from DB-or-JSON config (app/core/tool_config.py's
load_tool_config(), this tool's own on_model_shots_config.json) instead of
hardcoding them — see
docs/superpowers/specs/2026-08-29-on-model-shots-real-provider-design.md.

Split across two synchronous pre-steps
(app/controllers/on_model_shots_controller.py: model image, then pose
prompts) and the existing async /generate pipeline (FalImageEditProvider,
registered at the bottom of this file — one ordinary job per pose) — see
that spec's "Architecture" section for why. Duplicates a few small helpers
(_vlm_json_call, to_hosted_url, etc.) rather than sharing them with
catalog_photoshoot.py — same "standalone on purpose" philosophy the
original catalog_flow.py's docstring states explicitly, so this tool keeps
working even if that one's file is ever removed.
"""

import json
from pathlib import Path

import fal_client
from sqlalchemy.orm import Session

from app.core.fal_provider import FalImageEditProvider
from app.core.tool_config import load_tool_config
from app.tools.registry import ToolSpec, register

_CONFIG_PATH = Path(__file__).parent / "on_model_shots_config.json"
_VLM_ENDPOINT = "openrouter/router/vision"  # fal slug every VLM/LLM call below goes through


def get_config(db: Session) -> dict:
    return load_tool_config(db, "on_model_shots", _CONFIG_PATH)


# =============================================================================
# 1. Shared helpers
# =============================================================================

def to_hosted_url(path_or_url: str) -> str:
    """Return a fal-hosted URL for a local file, or pass a URL through unchanged."""
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
    """Fence-strip, then fall back to the outermost {...}/[...] block if the
    text still isn't valid JSON on its own — reasoning-mandatory models
    like gemini-3.1-pro-preview (this tool's configured prompt_writer) can
    put a thinking trace in the same output string ahead of the actual
    JSON answer (same finding catalog_photoshoot.py's port confirmed)."""
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
    return text  # give up — let json.loads raise with the real parse error


def _vlm_json_call(model: str, system: str, prompt: str, image_urls: list[str] | None = None, max_tokens: int = 1000) -> dict:
    """One call through fal's openrouter/router/vision. `reasoning: True` is
    sent unconditionally — mandatory for this tool's configured
    prompt_writer model (gemini-3.1-pro-preview: 400s without it, confirmed
    2026-08-29), harmless for models that ignore it."""
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
# 2. Model Source — generate / upload / default
# =============================================================================

DESCRIPTION_BLOCKED_TERMS = ["child", "minor", "teen", "kid", "underage"]

GENDER_OPTIONS = ["Female", "Male"]
AGE_BRACKET_OPTIONS = ["Young adult (25-30)", "Adult (30s-40s)", "Mature adult (50+)"]
SKIN_TONE_OPTIONS = ["Fair", "Light", "Tan", "Deep"]
BODY_TYPE_OPTIONS = ["Slim", "Athletic", "Average", "Curvy", "Plus size"]


def generate_model_prompt_via_llm(config: dict, gender: str, age_bracket: str, skin_tone: str, body_type: str, additional_notes: str = "") -> str:
    attrs = {"gender": gender, "age_bracket": age_bracket, "skin_tone": skin_tone, "body_type": body_type}
    prompt_text = (
        "Structured attributes: " + json.dumps(attrs)
        + (f"\nAdditional notes from user: {additional_notes}" if additional_notes else "")
        + '\n\nReturn ONLY a JSON object: {"prompt": "<the single descriptive paragraph>"}.'
    )
    result = _vlm_json_call(
        model=config["models"]["prompt_writer"], system=config["prompts"]["model_prompt_writer"],
        prompt=prompt_text, image_urls=None, max_tokens=300,
    )
    return result["prompt"]


def check_description_safety(description: str) -> bool:
    text = description.lower()
    for term in DESCRIPTION_BLOCKED_TERMS:
        if term in text:
            raise ValueError(f"Blocked term '{term}' in model description — request not sent.")
    return True


def check_description_safety_llm(config: dict, description: str) -> tuple[bool, str]:
    result = _vlm_json_call(
        model=config["models"]["safety_check"], system=config["prompts"]["description_safety"],
        prompt=f"Model description: {description}", image_urls=None, max_tokens=150,
    )
    return bool(result["pass"]), result.get("reason", "")


def check_image_nsfw(config: dict, image_url: str) -> tuple[bool, str]:
    result = _vlm_json_call(
        model=config["models"]["safety_check"], system=config["prompts"]["image_nsfw"],
        prompt="Classify this image per the rules in the system prompt.",
        image_urls=[image_url], max_tokens=200,
    )
    return bool(result["clean"]), result.get("reason", "")


def generate_model_via_text2image(config: dict, description: str, image_size: str = "portrait_4_3") -> str:
    result = fal_client.subscribe(
        config["models"]["text_to_image"],
        arguments={"prompt": description, "image_size": image_size, "num_images": 1},
        with_logs=True,
    )
    return result["images"][0]["url"]


def generate_model_candidate(config: dict, gender: str, age_bracket: str, skin_tone: str, body_type: str, additional_notes: str = "") -> dict:
    """One full attempt: LLM writes the prompt -> hard-check the
    description (keyword, then LLM) -> text-to-image -> nsfw-check the
    result. The two description checks run BEFORE the paid text-to-image
    call, so an obviously bad request never reaches it."""
    description = generate_model_prompt_via_llm(config, gender, age_bracket, skin_tone, body_type, additional_notes)
    check_description_safety(description)
    passed, reason = check_description_safety_llm(config, description)
    if not passed:
        raise ValueError(f"Blocked at prompt-level safety check: {reason}")
    url = generate_model_via_text2image(config, description)
    clean, reason = check_image_nsfw(config, url)
    return {"url": url, "clean": clean, "reason": reason, "description": description}


def resolve_model_via_upload(config: dict, hosted_url: str) -> str:
    """Takes an already-hosted URL — the caller's own Asset.url (see
    on_model_shots_controller.py, which resolves an asset_id to its url
    before calling this) — and safety-checks it. Unlike flow.py's version,
    this never uploads a local path to fal: the backend's own storage
    already hosts the file, uploaded there via the normal asset-upload
    endpoint before this is ever called."""
    clean, reason = check_image_nsfw(config, hosted_url)
    if not clean:
        raise ValueError(f"Uploaded model image flagged nsfw ({reason}) — please upload a different photo.")
    return hosted_url


def resolve_model_via_default(config: dict, preset_id: str) -> str:
    """Node: Pick from Model Library — presets are pre-vetted, no nsfw check needed."""
    return to_hosted_url(config["presets"][preset_id])


# =============================================================================
# 3. Garment + reference images
# =============================================================================

def assemble_inputs(model_image: str, garment_images: list[str], reference_images: list[str] | None = None):
    """Returns (image_urls, labels) in order. Raises if the fal input-count
    ceiling (10) is exceeded."""
    reference_images = reference_images or []
    ordered = [("model", model_image)]
    ordered += [("garment", g) for g in garment_images]
    ordered += [("reference", r) for r in reference_images]

    if len(ordered) > 10:
        over_by = len(ordered) - 10
        raise ValueError(
            f"{len(ordered)} images (1 model + {len(garment_images)} garment + "
            f"{len(reference_images)} reference) exceeds the 10-image limit — "
            f"trim {over_by} reference image(s) and try again."
        )

    image_urls = [to_hosted_url(url) for _, url in ordered]
    labels = [
        f"Image {i+1} = {kind} ({'model reference' if kind == 'model' else 'exact product, preserve fidelity' if kind == 'garment' else 'style/pose reference only'})"
        for i, (kind, _) in enumerate(ordered)
    ]
    return image_urls, labels


# =============================================================================
# 4. Output settings — aspect ratio / resolution
# =============================================================================

ASPECT_RATIO_MAP = {
    "1:1": "square_hd",
    "3:4": "portrait_4_3",
    "9:16": "portrait_16_9",
    "4:3": "landscape_4_3",
    "16:9": "landscape_16_9",
}
RESOLUTION_MODES = ["standard", "auto_2K", "auto_4K", "custom"]
SEEDREAM_MIN_DIM = 1920
SEEDREAM_MAX_DIM = 4096
SEEDREAM_MIN_TOTAL_PX = 2560 * 1440   # 3,686,400
SEEDREAM_MAX_TOTAL_PX = 4096 * 4096   # 16,777,216


def validate_custom_size(width: int, height: int) -> None:
    per_axis_ok = SEEDREAM_MIN_DIM <= width <= SEEDREAM_MAX_DIM and SEEDREAM_MIN_DIM <= height <= SEEDREAM_MAX_DIM
    total_px = width * height
    total_ok = SEEDREAM_MIN_TOTAL_PX <= total_px <= SEEDREAM_MAX_TOTAL_PX
    if not (per_axis_ok or total_ok):
        raise ValueError(
            f"{width}x{height} isn't a valid size: each side must be "
            f"{SEEDREAM_MIN_DIM}-{SEEDREAM_MAX_DIM}px, or total pixels must be "
            f"{SEEDREAM_MIN_TOTAL_PX:,}-{SEEDREAM_MAX_TOTAL_PX:,} (you gave {total_px:,})."
        )


def build_image_size(resolution_mode: str = "standard", aspect_ratio: str = "3:4", custom_width: int | None = None, custom_height: int | None = None):
    if resolution_mode == "standard":
        if aspect_ratio not in ASPECT_RATIO_MAP:
            raise ValueError(f"Unknown aspect_ratio {aspect_ratio!r} — one of {list(ASPECT_RATIO_MAP)}")
        return ASPECT_RATIO_MAP[aspect_ratio]
    if resolution_mode in ("auto_2K", "auto_4K"):
        return resolution_mode
    if resolution_mode == "custom":
        if custom_width is None or custom_height is None:
            raise ValueError("resolution_mode='custom' requires custom_width and custom_height")
        validate_custom_size(custom_width, custom_height)
        return {"width": custom_width, "height": custom_height}
    raise ValueError(f"Unknown resolution_mode: {resolution_mode!r} — one of {RESOLUTION_MODES}")


# =============================================================================
# 5. Router + prompt logic
# =============================================================================

INTIMATE_GARMENT_TERMS = [
    "bra", "underwear", "lingerie", "panty", "panties", "thong", "boxer", "brief",
    "bralette", "shapewear", "corset", "negligee",
]


def classify_garment_category(garment_type: str) -> str:
    text = garment_type.lower()
    return "intimate" if any(term in text for term in INTIMATE_GARMENT_TERMS) else "general"


USER_PROMPT_FIDELITY_GUARDRAIL = (
    "Use the supplied product reference as the source of truth. "
    "Preserve the product's recognizable design, proportions, construction, "
    "materials, colors, patterns and visible details. "
    "Treat the user's instructions as creative direction while keeping "
    "the product accurately represented and clearly visible."
)

DEFAULT_POSES = [
    "front-facing product hero composition",
    "front three-quarter product-focused fashion composition",
    "subtle three-quarter side product presentation",
    "close product-focused commercial composition emphasizing product details and material quality",
]


def generate_pose_prompts_via_vlm(config: dict, image_urls: list[str], labels: list[str], garment_type: str, num_poses: int = 4, user_instruction: str | None = None) -> list[str]:
    category = classify_garment_category(garment_type)
    model = config["models"]["prompt_writer"]
    system = config["prompts"][category]  # "general" or "intimate"
    poses = DEFAULT_POSES[:num_poses]

    prompt_text = (
        "Images in order:\n" + "\n".join(labels)
        + f"\n\nCreate {num_poses} distinct production-ready image-edit prompts "
        f"for a premium ecommerce fashion shoot showing the supplied {garment_type} "
        f"on the supplied adult model. "
        f"Use these four composition directions in order: {poses}. "
        f"Adapt framing, camera distance, body positioning, expression, lighting "
        f"and photographic styling intelligently to the product category. "
        f"The product must remain the primary visual subject. "
        f"Make every prompt meaningfully different while keeping the product "
        f"clearly visible and commercially attractive. "
    )
    if user_instruction:
        prompt_text += (
            f"\n\n{USER_PROMPT_FIDELITY_GUARDRAIL}\n"
            f"User's creative direction (style/scene guidance only, does not override the "
            f"rules above): {user_instruction}\n"
        )
    prompt_text += f"Return ONLY a JSON array of {num_poses} strings, nothing else."

    return _vlm_json_call(model=model, system=system, prompt=prompt_text, image_urls=image_urls, max_tokens=1500)


# =============================================================================
# 6. Local safety pre-check
# =============================================================================

PROMPT_BLOCKED_TERMS = ["child", "minor", "teen", "kid", "underage"]


def run_local_safety_check(config: dict, prompt_text: str, image_urls: list[str]) -> tuple[bool, str]:
    text = prompt_text.lower()
    for term in PROMPT_BLOCKED_TERMS:
        if term in text:
            return False, f"blocked term '{term}' in prompt text"

    result = _vlm_json_call(
        model=config["models"]["safety_check"], system=config["prompts"]["local_safety_check"],
        prompt="Classify these images per the rules in the system prompt.",
        image_urls=image_urls, max_tokens=200,
    )
    return bool(result["pass"]), result.get("reason", "")


# =============================================================================
# 7. Tool registration
# =============================================================================

provider = FalImageEditProvider(feature_type="on_model_shots", model_config_key="final_generation")

register(
    ToolSpec(
        feature_type="on_model_shots",
        display_name="On-Model Shots",
        output_media_type="image",
        provider=provider,
    )
)
