"""How many credits does THIS generation cost. Three tiers of precedence —
see BOOK.md Chapter 17 for the full "why" (this mirrors how Leonardo/
RunwayML/Civitai-style platforms price: base cost is really driven by which
MODEL runs, modified by settings like resolution, occasionally overridden
entirely by a template that wraps different backend logic).
"""

from sqlalchemy.orm import Session

from app.models.ai_model import AIModel
from app.models.template import Template
from app.models.tool import Tool


def resolve_credit_cost(db: Session, feature_type: str, input_payload: dict) -> int:
    template_id = input_payload.get("template_id")
    if template_id:
        template = db.get(Template, template_id)
        if template and template.credit_cost_override is not None:
            return template.credit_cost_override

    tool = db.get(Tool, feature_type)
    if tool is None:
        return 1  # defensive default — schemas/generation.py already
        # rejects a genuinely unknown feature_type before this is ever
        # reached; this only guards a race where a tool vanished mid-request.

    model_id = input_payload.get("model_id") or tool.default_model_id
    if model_id is None:
        # No model concept at all for this tool (every tool that exists
        # today) — the flat fallback, unmodified.
        return tool.credit_cost

    model = db.get(AIModel, model_id)
    base = model.base_credit_cost if model else tool.credit_cost

    multiplier = 1
    if tool.pricing_config:
        resolution = input_payload.get("resolution")
        multipliers = tool.pricing_config.get("resolution_multipliers", {})
        if resolution and resolution in multipliers:
            multiplier = multipliers[resolution]

    return base * multiplier
