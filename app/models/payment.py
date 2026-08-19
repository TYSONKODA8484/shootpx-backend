import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.core.db import Base
from app.models.team import new_id


class PaymentStatus(str, enum.Enum):
    captured = "captured"
    failed = "failed"
    refunded = "refunded"


class PaymentKind(str, enum.Enum):
    subscription_charge = "subscription_charge"
    topup = "topup"


class Payment(Base):
    """Our own reconciliation record of every provider charge processed —
    independent of re-querying the provider. provider_payment_id is UNIQUE:
    this is also the idempotency guard for webhook processing (a redelivered
    webhook event is detected by checking for this id BEFORE granting any
    credit — see core/credits.py). Not a compliant invoice, just enough to
    answer "what happened" without hitting Razorpay's API."""

    __tablename__ = "payments"

    id = Column(String, primary_key=True, default=new_id)
    team_id = Column(String, ForeignKey("teams.id"), nullable=False, index=True)
    provider = Column(String, nullable=False)
    provider_payment_id = Column(String, nullable=False, unique=True)
    provider_order_id = Column(String, nullable=True)
    provider_subscription_id = Column(String, nullable=True)
    amount = Column(Integer, nullable=False)
    currency = Column(String, nullable=False, default="INR")
    status = Column(String, nullable=False)  # PaymentStatus value
    kind = Column(String, nullable=False)  # PaymentKind value
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
