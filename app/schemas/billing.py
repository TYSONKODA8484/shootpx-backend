from pydantic import BaseModel, ConfigDict, computed_field


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str  # internal id — kept for back-compat, not what the frontend should submit to /billing/subscribe
    provider_plan_id: str | None  # Razorpay's own plan id; null for Free
    name: str
    billing_cycle: str
    price: int | None
    currency: str
    region: str | None  # e.g. "IN", "US"; null for the region-less Free plan
    plan_group: str | None  # ties regional variants of the same tier together, e.g. "pro-monthly"
    credit_allowance: int
    max_team_members: int
    badge: str | None  # e.g. "BEST VALUE"; null if none
    features: list[str] | None  # bullet list for the pricing page

    @computed_field  # type: ignore[prop-decorator]
    @property
    def plan_id(self) -> str:
        """What /billing/subscribe expects back as `plan_id`: the Razorpay
        plan id for a paid plan, or the literal string "free" for the Free
        plan (which has no provider_plan_id at all) — see
        billing_controller.create_subscription's "cannot subscribe to
        Free directly" check, so the frontend never actually POSTs this
        value for Free, but it still needs SOME stable identifier to key
        off in a plan list/selector."""
        return self.provider_plan_id or "free"

class CreditPackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    credit_amount: int
    price: int
    currency: str
    region: str | None
    pack_group: str | None
    badge: str | None
    features: list[str] | None

class SubscribeRequest(BaseModel):
    team_id: str
    plan_id: str  # accepts EITHER the internal plans.id OR a paid plan's provider_plan_id (see PlanOut.plan_id)


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


class BillingConfigOut(BaseModel):
    """Which pricing-page tab(s) are currently offered — see
    app/models/billing_mode.py's docstring. A well-behaved frontend calls
    this once and hides the Subscription tab entirely when
    subscriptions_enabled is false (same for credits_enabled/Credits tab),
    rather than showing an empty or broken tab."""
    subscriptions_enabled: bool
    credits_enabled: bool
