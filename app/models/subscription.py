import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String

from app.core.db import Base
from app.models.team import new_id


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    past_due = "past_due"
    cancelled = "cancelled"
    free = "free"


class TeamSubscription(Base):
    """One row per team — which plan they're on and whether it's currently
    paid for. next_credit_refill_at drives core/credits.py's refill cron and
    is set for EVERY team, Free included, so the same mechanism grants
    credits uniformly regardless of plan type. The FIRST grant for any team
    is always synchronous (create_personal_team / the subscribe webhook
    handler), never waits on the cron — see core/credits.py's docstring."""

    __tablename__ = "team_subscriptions"

    id = Column(String, primary_key=True, default=new_id)
    team_id = Column(String, ForeignKey("teams.id"), nullable=False, unique=True)
    plan_id = Column(String, ForeignKey("plans.id"), nullable=False)
    provider = Column(String, nullable=True)  # null while on Free
    provider_subscription_id = Column(String, nullable=True)  # null while on Free
    status = Column(String, nullable=False, default=SubscriptionStatus.free.value)
    current_period_end = Column(DateTime, nullable=True)  # null for Free
    next_credit_refill_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
