from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String

from app.core.db import Base
from app.core.time import utc_now


class Tool(Base):
    """A DB-backed mirror of the in-memory app/tools/ registry
    (app/tools/registry.py's TOOLS dict). Code stays the source of truth for
    a tool's BEHAVIOR — feature_type/display_name/output_media_type are
    synced from the registry on every boot (app/tools/sync.py) and never
    edited here. This table exists for what SHOULDN'T require a redeploy:
    credit_cost/pricing_config/is_active/status are DB-owned, left untouched
    by that sync once a row exists, so an admin's pricing/visibility
    decisions survive every restart.

    is_active vs status — two different axes, not a duplicate pair:
      - is_active=False: gone from GET /tools entirely (the existing
        kill-switch, unchanged) — used for a tool that shouldn't be
        mentioned to a client at all right now.
      - status: only meaningful when is_active=True. "live" is shown
        normally and callable via /generate. "coming_soon" is STILL
        RETURNED by GET /tools (so the frontend can render it with a SOON
        badge) but generation_controller/product_import_controller reject
        it the same way an inactive tool is rejected — advertised, not
        callable yet. There is deliberately no third status value doing
        what is_active=False already does; "hidden" would just be
        is_active=False again under a different name.
    """

    __tablename__ = "tools"

    feature_type = Column(String, primary_key=True)  # code-owned
    display_name = Column(String, nullable=False)  # code-owned
    output_media_type = Column(String, nullable=False)  # code-owned
    default_model_id = Column(String, ForeignKey("ai_models.model_id"), nullable=True)
    # ^ code-owned. Set when this tool offers model selection. NULL means
    # this tool has no model concept — core/pricing.py falls back to
    # credit_cost below. The FK constraint was deliberately deferred until
    # ai_models existed (see the Spec A -> Spec B sequencing note) — added
    # now that it does.

    credit_cost = Column(Integer, nullable=False, default=1)  # DB-owned
    pricing_config = Column(JSON, nullable=True)  # DB-owned. e.g.
    # {"resolution_multipliers": {"2k": 1, "4k": 2}} — unused until a
    # pricing engine reads it; harmless sitting here in the meantime.
    is_active = Column(Boolean, nullable=False, default=True)  # DB-owned
    status = Column(String, nullable=False, default="live")  # DB-owned. 'live' | 'coming_soon'

    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
