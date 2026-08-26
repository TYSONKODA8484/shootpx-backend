from sqlalchemy import JSON, Boolean, Column, ForeignKey, Integer, String

from app.core.db import Base
from app.models.team import new_id


class Template(Base):
    """A preset that can override computed pricing entirely via
    credit_cost_override. See core/pricing.py's resolve_credit_cost() for
    the full precedence order this participates in — a template's override,
    when set, always wins outright over the model+modifier calculation."""

    __tablename__ = "templates"

    id = Column(String, primary_key=True, default=new_id)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)  # "Photoshoot" | "Mockup" |
    # "On-model" | "Motion" | "UGC" — a plain string, not an enum, same
    # lightweight-string convention as GenerationJob.feature_type/batch_id.
    preview_asset_url = Column(String, nullable=True)  # null until a real
    # preview image exists for this template — seeding a fake URL would be
    # dishonest catalog data (see BACKEND-NEEDS.md's B3 section).
    feature_type = Column(String, ForeignKey("tools.feature_type"), nullable=False)
    model_id = Column(String, ForeignKey("ai_models.model_id"), nullable=True)
    preset_payload = Column(JSON, nullable=False, default=dict)  # fixed
    # input_payload fields this template forces
    credit_cost_override = Column(Integer, nullable=True)  # if set, wins
    # outright over any computed cost
    is_active = Column(Boolean, nullable=False, default=True)
