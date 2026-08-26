"""mockup_studio — places a design onto an apparel/packaging/device mockup.
Routes to MockAIProvider for now, same as every other tool. input_payload:
{ mockup_type: "apparel"|"packaging"|"device", prompt }.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="mockup_studio",
        display_name="Mockup Studio",
        output_media_type="image",
        provider=ai_provider,
    )
)
