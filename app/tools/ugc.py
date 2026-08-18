"""ugc — generates a UGC-style video from an uploaded asset. Routes to
MockAIProvider for now, same as every other tool. See on_model_shots.py
for the pattern this file follows.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="ugc",
        display_name="UGC Video",
        output_media_type="video",
        provider=ai_provider,
    )
)
