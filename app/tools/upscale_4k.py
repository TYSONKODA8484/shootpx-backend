"""upscale_4k — upscales an image to 4K. Routes to MockAIProvider for now,
same as every other tool. input_payload: { target_px: 4096 }. Marking this
PRO-only (per BACKEND-NEEDS.md) is deferred until a plan-gating system
exists — nothing enforces it yet.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="upscale_4k",
        display_name="Upscale 4K",
        output_media_type="image",
        provider=ai_provider,
    )
)
