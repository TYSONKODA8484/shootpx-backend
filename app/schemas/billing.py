from pydantic import BaseModel


class PlanOut(BaseModel):
    id: str
    name: str
    billing_cycle: str
    price: int | None
    currency: str
    credit_allowance: int
    max_team_members: int

    class Config:
        from_attributes = True


class CreditPackOut(BaseModel):
    id: str
    name: str
    credit_amount: int
    price: int
    currency: str

    class Config:
        from_attributes = True


class SubscribeRequest(BaseModel):
    team_id: str
    plan_id: str


class CancelRequest(BaseModel):
    team_id: str


class TopupRequest(BaseModel):
    team_id: str
    credit_pack_id: str


class ConfirmPaymentRequest(BaseModel):
    """What Razorpay Checkout's own `handler` callback hands back — passed
    straight through so we can verify it ourselves (core/payment_provider.py's
    verify_order_payment/verify_subscription_payment), no webhook needed.
    Exactly one of razorpay_order_id / razorpay_subscription_id is set,
    depending on whether this was a top-up or a subscription."""
    razorpay_payment_id: str
    razorpay_order_id: str | None = None
    razorpay_subscription_id: str | None = None
    razorpay_signature: str


class CheckoutOut(BaseModel):
    """Whatever the provider's checkout needs — deliberately a free-form
    dict on the provider side (core/payment_provider.py), typed loosely
    here too since a different provider's checkout needs different fields."""
    provider: str
    checkout: dict


class CreditTransactionOut(BaseModel):
    amount: int
    reason: str
    reference_id: str | None
    balance_after: int
    created_at: str


class BillingStatusOut(BaseModel):
    team_id: str
    plan: PlanOut
    subscription_status: str
    current_period_end: str | None
    balance: int
    recent_transactions: list[CreditTransactionOut]
