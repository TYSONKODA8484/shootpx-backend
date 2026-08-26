"""relight_shadows — re-lights a product shot and adjusts its shadows.
Routes to MockAIProvider for now, same as every other tool. input_payload:
{ key_angle_deg, softness: "soft"|"hard", warmth_k }.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="relight_shadows",
        display_name="Relight & Shadows",
        output_media_type="image",
        provider=ai_provider,
    )
)
