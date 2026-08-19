import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.core.db import Base
from app.models.team import new_id


class BillingCycle(str, enum.Enum):
    monthly = "monthly"
    yearly = "yearly"
    free = "free"


class Plan(Base):
    """A subscription tier. Ships with one placeholder Free plan (seeded by
    migration) — real pricing tiers are business data, populated whenever
    they're decided, no code change needed either way.

    credit_allowance is granted PER MONTHLY REFILL regardless of
    billing_cycle — a yearly plan still gets this amount granted every
    month, not 12x on day one (core/credits.py's refill cron). provider/
    provider_plan_id are null for the Free plan (no payment provider
    involved at all); both null-together or set-together for a paid plan.
    """

    __tablename__ = "plans"

    id = Column(String, primary_key=True, default=new_id)
    name = Column(String, nullable=False)
    billing_cycle = Column(String, nullable=False)  # 'monthly' | 'yearly' | 'free'
    price = Column(Integer, nullable=True)  # smallest currency unit (paise); null for Free
    currency = Column(String, nullable=False, default="INR")
    credit_allowance = Column(Integer, nullable=False)
    max_team_members = Column(Integer, nullable=False)
    provider = Column(String, nullable=True)  # e.g. "razorpay"; null for Free
    provider_plan_id = Column(String, nullable=True)  # the provider's own plan id; null for Free
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
