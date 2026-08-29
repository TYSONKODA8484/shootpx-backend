"""creative_photoshoot — one free-form creative image per Generate click,
no batch/num_images setting anywhere (a second variation is a second full
flow re-run, safety check included, not a fan-out). Third tool alongside
on_model_shots.py and catalog_photoshoot.py — real port of the verified-
against-real-fal.ai-calls creative_flow.py.

Fully self-contained config, same pattern as the other two tools: this
tool's own tool_config row (feature_type="creative_photoshoot") holds all
3 models it needs — catalog_generation (bytedance/seedream/v5/lite/edit,
same model Catalog Photoshoot uses, confirmed 2026-08-29), prompt_writer,
and safety_check — plus its own copy of the safety-check system prompt.
No runtime dependency on catalog_photoshoot's config row; each tool's
config is independently editable, even though today's values happen to
match.

Still reuses catalog_photoshoot.py's already-debugged CODE directly
(assemble_product_images, run_safety_check, _vlm_json_call,
build_image_size) rather than duplicating those functions — only the
config values are duplicated (in JSON/DB), not the logic. This is a
deliberate exception to on_model_shots.py/catalog_photoshoot.py's own
"duplicate rather than share" convention for the functions themselves
(see creative_flow.py's own docstring: re-deriving the VLM-call
reasoning-mode fix a third time would reintroduce a bug class already
fixed once) — combined with fully independent config per tool.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.fal_provider import FalImageEditProvider
from app.core.tool_config import load_tool_config
from app.tools import catalog_photoshoot as catalog_tool
from app.tools.registry import ToolSpec, register

_CONFIG_PATH = Path(__file__).parent / "creative_photoshoot_config.json"


def get_config(db: Session) -> dict:
    return load_tool_config(db, "creative_photoshoot", _CONFIG_PATH)


IDEA_OPTIONS = [
    "Lifestyle / in-use scene",
    "Studio hero shot",
    "Outdoor / nature setting",
    "Minimalist flat lay",
    "Editorial / fashion",
    "Seasonal / festive",
    "Social media story (vertical)",
    "Moody / dramatic lighting",
    "Bright & airy",
    "Product-in-hand close-up",
]


# =============================================================================
# Adult-floor guardrail — applied to EVERY final prompt before generation,
# regardless of which case produced it (including the verbatim-user-prompt
# case, which never touches an LLM). Cheap, unconditional, harmless if no
# person ends up in the scene.
# =============================================================================

ADULT_FLOOR_GUARDRAIL = (
    "If this scene includes any person, they must be a clearly adult, professional "
    "photography subject — mature adult facial structure and proportions, never a minor. "
)


def apply_adult_floor(prompt: str) -> str:
    return ADULT_FLOOR_GUARDRAIL + prompt


# =============================================================================
# Case branching — exactly one of three shapes, one final_prompt out
# =============================================================================

def build_creative_prompt(
    config: dict, image_urls: list[str], labels: list[str],
    idea_tags: list[str] | None = None, user_prompt: str | None = None,
) -> str:
    """Case 1 (prompt only): used verbatim, no LLM call — the whole point
    of that case is skipping the LLM entirely. Case 2 (idea only) / Case 3
    (idea + prompt): one LLM+Vision call either way, via
    catalog_photoshoot's _vlm_json_call (same VLM-call plumbing, not a
    re-derived copy)."""
    idea_tags = idea_tags or []
    if not idea_tags and not user_prompt:
        raise ValueError("Provide an idea, a prompt, or both — Generate needs at least one.")

    if user_prompt and not idea_tags:
        return user_prompt

    prompt_text = (
        "Product reference images, in order:\n" + "\n".join(labels)
        + f"\n\nCreative idea tag(s): {', '.join(idea_tags)}"
    )
    if user_prompt:
        prompt_text += f"\nUser's additional instruction (merge with the idea into one refined prompt): {user_prompt}"
    prompt_text += '\n\nReturn ONLY a JSON object: {"prompt": "<the single final prompt>"}.'

    result = catalog_tool._vlm_json_call(
        model=config["models"]["prompt_writer"], system=config["prompts"]["creative_prompt_writer"],
        prompt=prompt_text, image_urls=image_urls, max_tokens=500,
    )
    return result["prompt"]


# =============================================================================
# Tool registration — its own FalImageEditProvider instance, reading this
# tool's own config row (feature_type="creative_photoshoot"), not
# catalog_photoshoot's.
# =============================================================================

provider = FalImageEditProvider(feature_type="creative_photoshoot", model_config_key="catalog_generation")

register(
    ToolSpec(
        feature_type="creative_photoshoot",
        display_name="Creative Photoshoot",
        output_media_type="image",
        provider=provider,
    )
)
