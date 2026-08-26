"""resize_outpaint — extends an image's canvas via outpainting. Routes to
MockAIProvider for now, same as every other tool. input_payload:
{ direction: "all"|"horizontal"|"vertical", amount_pct }.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="resize_outpaint",
        display_name="Resize & Outpaint",
        output_media_type="image",
        provider=ai_provider,
    )
)
