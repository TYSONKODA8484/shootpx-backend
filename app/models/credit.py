import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.core.db import Base
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
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CreditPack(Base):
    """A purchasable one-off top-up amount. No provider-side pre-
    registration needed — a one-time Razorpay Order is created with an
    arbitrary amount directly, this is just our own catalog of what's
    offered."""

    __tablename__ = "credit_packs"

    id = Column(String, primary_key=True, default=new_id)
    name = Column(String, nullable=False)
    credit_amount = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)  # smallest currency unit
    currency = Column(String, nullable=False, default="INR")
    is_active = Column(Boolean, nullable=False, default=True)
