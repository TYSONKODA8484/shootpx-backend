"""magic_erase — removes a brushed-out region of an image. Routes to
MockAIProvider for now, same as every other tool. input_payload:
{ mask_data_url, strength: 0-100, feather_px } — the frontend sends the
brush mask as a base64 data URL since there's no "upload a second file
alongside the request" shape in /generate today (see BACKEND-NEEDS.md's
note on mask-based tools; revisit as a real Asset with kind="mask" only if
payload size becomes a real problem).
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="magic_erase",
        display_name="Magic Erase",
        output_media_type="image",
        provider=ai_provider,
    )
)
