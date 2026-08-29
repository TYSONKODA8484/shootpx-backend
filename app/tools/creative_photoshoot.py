"""creative_photoshoot — one free-form creative image per Generate click,
no batch/num_images setting anywhere (a second variation is a second full
flow re-run, safety check included, not a fan-out). Third tool alongside
on_model_shots.py and catalog_photoshoot.py — real port of the verified-
against-real-fal.ai-calls creative_flow.py.

Deliberately thin, same as creative_flow.py: reuses catalog_photoshoot.py's
already-debugged functions directly (assemble_product_images,
run_safety_check, _vlm_json_call, build_image_size) rather than
duplicating them. This tool's generation targets the SAME model catalog
uses (bytedance/seedream/v5/lite/edit, confirmed 2026-08-29), so
catalog_photoshoot's config/logic is directly correct here, not a copy of
it — a deliberate exception to on_model_shots.py/catalog_photoshoot.py's
own "duplicate rather than share" convention (see creative_flow.py's own
docstring: re-deriving the VLM-call reasoning-mode fix a third time would
reintroduce a bug class already fixed once).

Only this tool's own prompt_writer model + creative system prompt live in
its own tool_config row (feature_type="creative_photoshoot") — the
generation model and safety-check model/prompt are read from
catalog_photoshoot's config at call time, always, never copied. This tool
also registers against catalog_photoshoot's own FalImageEditProvider
INSTANCE (not a second one) — same generation model, same config row.
"""

from pathlib import Path

from sqlalchemy.orm import Session

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
# Tool registration — shares catalog_photoshoot's FalImageEditProvider
# instance directly (same generation model, same config row) rather than
# constructing a second one.
# =============================================================================

register(
    ToolSpec(
        feature_type="creative_photoshoot",
        display_name="Creative Photoshoot",
        output_media_type="image",
        provider=catalog_tool.provider,
    )
)
