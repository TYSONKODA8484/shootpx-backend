"""product_motion — generates a short product motion clip (orbit, push-in,
pour, unbox, etc). Routes to MockAIProvider for now, same as every other
tool. Also backs the UGC tab's "Effect Templates" tile — that's this same
feature_type with a specific `motion` preset, not a separate registration.
input_payload: { motion: "orbit"|"push-in"|"pan"|"zoom-out"|"pour"|"unbox",
aspect: "9:16"|"16:9", duration_s: 5, notes }.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="product_motion",
        display_name="Product Motion",
        output_media_type="video",
        provider=ai_provider,
    )
)
