"""product_photoshoot — the core "stage a product photo, generate" tool.
Routes to MockAIProvider for now, same as every other tool. See
on_model_shots.py for the pattern this file follows. input_payload (from
the frontend): { prompt, mode: "precise"|"creative",
aspect: "1:1"|"4:5"|"16:9"|"9:16", variations: 1-8, brand_kit_on: bool } —
unvalidated for now, per BACKEND-NEEDS.md's explicit recommendation (no real
AIProvider exists yet to dictate a required shape).
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="product_photoshoot",
        display_name="Product Photoshoot",
        output_media_type="image",
        provider=ai_provider,
    )
)
