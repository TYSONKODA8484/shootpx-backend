import enum

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String

from app.core.db import Base
from app.core.time import utc_now
from app.models.team import new_id


class CreditReason(str, enum.Enum):
    plan_grant = "plan_grant"
    topup_purchase = "topup_purchase"
    generation_spend = "generation_spend"
    refund = "refund"
    manual_adjustment = "manual_adjustment"
    subscription_cancelled = "subscription_cancelled"  # the clawback applied
    # when a paid subscription is cancelled — removes min(balance, plan's
    # credit_allowance), never more than what's actually left, so top-up
    # ("lifetime") credits bought separately are never touched by this.
    # See billing_controller.cancel_subscription / BOOK.md Chapter 17.
    export_spend = "export_spend"  # POST /assets/{id}/export — 1 credit
    # per requested preset, charged once for the whole call. Pure
    # image-processing, no AI provider involved, kept as its own reason so
    # it's distinguishable from generation_spend in the ledger/activity feed.


class TeamCreditBalance(Base):
    """The fast-read number /generate checks against. ALWAYS reconcilable
    against, never a substitute for, CreditTransaction below — that ledger
    is the source of truth; this is a cache of its running total. Updated
    via atomic SQL (core/credits.py's _grant_credits/_spend_credits), never
    read-then-write in Python — a webhook-driven grant and a worker-driven
    deduction can land at the same moment, and only deductions are
    protected by the per-team generation lock (app/worker.py)."""

    __tablename__ = "team_credit_balances"

    team_id = Column(String, ForeignKey("teams.id"), primary_key=True)
    balance = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class CreditTransaction(Base):
    """Append-only audit ledger — every grant/spend/refund/top-up, with a
    balance_after snapshot so a support question never needs the history
    replayed to answer it. This table, not TeamCreditBalance, is the real
    source of truth."""

    __tablename__ = "credit_transactions"

    id = Column(String, primary_key=True, default=new_id)
    team_id = Column(String, ForeignKey("teams.id"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)  # signed: +grant, -spend
    reason = Column(String, nullable=False)  # CreditReason value
    reference_id = Column(String, nullable=True)  # job id / payment id, depending on reason
    balance_after = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class CreditPack(Base):
    """A purchasable one-off top-up amount. No provider-side pre-
    registration needed — a one-time Razorpay Order is created with an
    arbitrary amount directly, this is just our own catalog of what's
    offered.

    region/pack_group mirror Plan's geo-pricing fields (see Plan's
    docstring) — not populated with any non-India rows yet, same reason as
    Plan (personal Razorpay accounts can't enable International Payments).

    features/badge mirror Plan's marketing-copy fields — the pricing
    page's bullet list and ribbon label (e.g. "MOST POPULAR") live here,
    not hardcoded in the frontend.
    """

    __tablename__ = "credit_packs"

    id = Column(String, primary_key=True, default=new_id)
    name = Column(String, nullable=False)
    credit_amount = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)  # smallest currency unit
    currency = Column(String, nullable=False, default="INR")
    region = Column(String, nullable=True)  # e.g. "IN", "US"; null if priced the same everywhere
    pack_group = Column(String, nullable=True)  # ties regional variants together, e.g. "small-topup"
    is_active = Column(Boolean, nullable=False, default=True)
    badge = Column(String, nullable=True)  # e.g. "MOST POPULAR"; null if none
    features = Column(JSON, nullable=True)  # ordered list of bullet strings for the pricing page
