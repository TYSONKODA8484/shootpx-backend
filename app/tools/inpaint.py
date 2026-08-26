"""inpaint — replaces a brushed-in region of an image with prompted
content. Routes to MockAIProvider for now, same as every other tool.
input_payload: { mask_data_url, prompt } — same mask-as-data-url note as
magic_erase.py.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="inpaint",
        display_name="Inpaint",
        output_media_type="image",
        provider=ai_provider,
    )
)
