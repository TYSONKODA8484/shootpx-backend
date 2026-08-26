"""flat_lay_angles — generates additional flat-lay/angle shots of a
product. Routes to MockAIProvider for now, same as every other tool.
input_payload: { angle_count: 1-4 }.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="flat_lay_angles",
        display_name="Flat Lay / Angles",
        output_media_type="image",
        provider=ai_provider,
    )
)
