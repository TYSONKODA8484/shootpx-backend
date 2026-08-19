"""Mirrors the in-memory tool registry (app/tools/registry.py's TOOLS dict)
into the tools DB table on every boot. See app/models/tool.py's docstring
for the code-owned vs DB-owned column split this respects.
"""

from sqlalchemy.orm import Session

from app.models.tool import Tool
from app.tools.registry import TOOLS


def sync_tools_to_db(db: Session) -> None:
    for spec in TOOLS.values():
        existing = db.get(Tool, spec.feature_type)
        if existing:
            existing.display_name = spec.display_name
            existing.output_media_type = spec.output_media_type
            # credit_cost, pricing_config, is_active, default_model_id are
            # DB-owned — never touched here on an existing row.
        else:
            db.add(Tool(
                feature_type=spec.feature_type,
                display_name=spec.display_name,
                output_media_type=spec.output_media_type,
            ))
    db.commit()
