"""on_model_shots — puts an uploaded product/garment shot on a model.
Routes to MockAIProvider for now, same as every other tool (no real
provider adapter exists yet). Once one does, this file is where its
request-building (input_payload -> that provider's actual request shape)
and response-parsing (that provider's result -> GenerationResult) logic
lives — nothing outside this file needs to change to add that.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="on_model_shots",
        display_name="On-Model Shots",
        output_media_type="image",
        provider=ai_provider,
    )
)
