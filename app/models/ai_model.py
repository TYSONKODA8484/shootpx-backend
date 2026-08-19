from sqlalchemy import Boolean, Column, Integer, String

from app.core.db import Base


class AIModel(Base):
    """The model-playground catalog — table name deliberately "ai_models",
    not "models", to avoid colliding with the app/models/ Python package.
    base_credit_cost is DB-editable, same philosophy as Tool.credit_cost.
    Tool.default_model_id (app/models/tool.py) points here once a tool
    offers model selection; core/pricing.py's resolve_credit_cost() is what
    actually reads this table."""

    __tablename__ = "ai_models"

    model_id = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    base_credit_cost = Column(Integer, nullable=False, default=1)
    provider_name = Column(String, nullable=False)  # which AI aggregator
    # (fal.ai, Segmind, ...) — independent of PaymentProvider, this is about
    # generation, not billing.
    is_active = Column(Boolean, nullable=False, default=True)
