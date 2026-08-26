"""Public template catalog — no auth, same spirit as GET /tools. A template
is a preset FOR a tool (its feature_type), not its own generation path —
applying one just pre-fills that tool's input_payload before the user
tweaks and hits /generate.
"""

from sqlalchemy.orm import Session

from app.models.template import Template
from app.models.tool import Tool
from app.schemas.templates import TemplateListOut, TemplateOut


def _effective_cost(template: Template, tool: Tool | None) -> int:
    if template.credit_cost_override is not None:
        return template.credit_cost_override
    return tool.credit_cost if tool else 1


def list_templates(
    db: Session,
    category: str | None = None,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> TemplateListOut:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    query = db.query(Template).filter(Template.is_active == True)  # noqa: E712
    if category:
        query = query.filter(Template.category == category)
    if q:
        query = query.filter(Template.name.ilike(f"%{q}%"))

    total = query.count()
    rows = query.order_by(Template.category, Template.name).offset(offset).limit(limit).all()

    feature_types = {t.feature_type for t in rows}
    tools_by_type = (
        {t.feature_type: t for t in db.query(Tool).filter(Tool.feature_type.in_(feature_types)).all()}
        if feature_types else {}
    )

    templates = [
        TemplateOut(
            id=t.id, name=t.name, category=t.category, feature_type=t.feature_type,
            credit_cost=_effective_cost(t, tools_by_type.get(t.feature_type)),
            preview_asset_url=t.preview_asset_url, input_payload_preset=t.preset_payload,
        )
        for t in rows
    ]
    return TemplateListOut(total=total, templates=templates)
