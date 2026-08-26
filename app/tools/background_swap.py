"""background_swap — replaces a product shot's background. Routes to
MockAIProvider for now, same as every other tool. input_payload:
{ prompt, aspect: "1:1"|"4:5"|"16:9"|"9:16" }.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="background_swap",
        display_name="Background Swap",
        output_media_type="image",
        provider=ai_provider,
    )
)
