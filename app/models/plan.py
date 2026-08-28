import enum

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String

from app.core.db import Base
from app.core.time import utc_now
from app.models.team import new_id


class BillingCycle(str, enum.Enum):
    weekly = "weekly"
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

    region/plan_group exist for GEO-PRICING (not populated with any
    non-India rows yet — personal Razorpay accounts can't enable
    International Payments, so there's nowhere to charge a non-INR card
    right now; the columns are just left in place for whenever a business
    account makes that possible). region is the ISO country code this
    row's price applies to; plan_group would tie regional variants of one
    tier together. The Free plan has both None: it's priced identically
    everywhere, no regional variant needed.

    provider_plan_id is what the FRONTEND/public API should treat as this
    plan's identifier for paid plans (billing_controller.create_subscription
    accepts either it or the internal id — see that function's docstring) —
    it's Razorpay's own plan_id, e.g. "plan_TV6uz8xD64BCHw", visible and
    verifiable directly in the Razorpay dashboard (Subscriptions > Plans),
    which the internal `id` (an opaque UUID) is not. `id` still exists and
    is still the real primary key — TeamSubscription.plan_id FKs to it,
    and the Free plan (which has no provider_plan_id at all) needs SOME
    identifier — but it's an implementation detail the frontend shouldn't
    need to care about for a paid plan.

    features is free-form marketing copy (a bullet list, e.g. ["2K export",
    "Commercial licence", "Priority generation queue"]) so the frontend's
    pricing page reads it from here instead of hardcoding it — same
    "DB-owned, not code-owned" idea as Tool.pricing_config.
    """

    __tablename__ = "plans"

    id = Column(String, primary_key=True, default=new_id)
    name = Column(String, nullable=False)
    billing_cycle = Column(String, nullable=False)  # 'weekly' | 'monthly' | 'yearly' | 'free'
    price = Column(Integer, nullable=True)  # smallest currency unit (paise/cents); null for Free
    currency = Column(String, nullable=False, default="INR")
    region = Column(String, nullable=True)  # e.g. "IN", "US"; null for Free (region-less)
    plan_group = Column(String, nullable=True)  # e.g. "pro-monthly"; ties regional variants together
    credit_allowance = Column(Integer, nullable=False)
    max_team_members = Column(Integer, nullable=False)
    provider = Column(String, nullable=True)  # e.g. "razorpay"; null for Free
    provider_plan_id = Column(String, nullable=True)  # the provider's own plan id; null for Free
    is_active = Column(Boolean, nullable=False, default=True)
    badge = Column(String, nullable=True)  # e.g. "BEST VALUE"; null if none
    features = Column(JSON, nullable=True)  # ordered list of bullet strings for the pricing page
    created_at = Column(DateTime, default=utc_now, nullable=False)
