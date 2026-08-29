from sqlalchemy import JSON, Column, DateTime, String

from app.core.db import Base
from app.core.time import utc_now


class ToolConfig(Base):
    """DB override for a tool's models/prompts. app/core/tool_config.py's
    load_tool_config() reads this first, falling back to a checked-in JSON
    file (app/tools/<feature_type>_config.json) when no row exists here or
    the DB isn't reachable at all — see
    docs/superpowers/specs/2026-08-29-on-model-shots-real-provider-design.md's
    "DB-backed models + prompts, JSON fallback" section. One row per
    feature_type; config_json's shape is entirely up to that tool's own
    file (app/tools/<feature_type>.py), not enforced here."""

    __tablename__ = "tool_config"

    feature_type = Column(String, primary_key=True)
    config_json = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
