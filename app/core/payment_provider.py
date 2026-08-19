"""The billing side's swappable seam — same pattern as core/storage.py and
core/ai_provider.py (see BOOK.md's "swappable-seam pattern"). One interface,
one implementation today (Razorpay). Every table that references an
external payment record stores BOTH a provider string and a provider_*_id
(app/models/plan.py, subscription.py, payment.py) — the same naming
convention GenerationJob.provider/external_job_id already established, not
a new one invented for billing. Adding Stripe/PayPal later means a new
PaymentProvider subclass and new rows with provider="stripe"; zero changes
to any shared billing logic (controllers/billing_controller.py,
core/credits.py, core/pricing.py).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import razorpay

from app.core.config import settings


class PaymentProviderError(Exception):
    """The provider itself rejected a request — e.g. Razorpay refusing to
    cancel a subscription that never actually entered a real billing cycle.
    Distinct from a network/connectivity failure: this is the provider's
    own considered answer, and its message is usually more useful to show
    a user than anything we'd invent (same philosophy as
    product_scraper_client's failure messages — see BOOK.md Chapter 14)."""


@dataclass
class SubscriptionHandle:
    provider: str
    provider_subscription_id: str
    checkout: dict[str, Any]  # whatever the frontend/console needs to open
    # checkout — for Razorpay: {"key_id": ..., "subscription_id": ...} to
    # hand straight to Razorpay Checkout.js. Deliberately a free-form dict,
    # not a fixed shape — a different provider's checkout needs different
    # fields, and nothing outside the provider implementation should care.


@dataclass
class OrderHandle:
    provider: str
    provider_order_id: str
    checkout: dict[str, Any]


class PaymentProvider(ABC):
    @abstractmethod
    def create_subscription(self, provider_plan_id: str, notes: dict[str, str]) -> SubscriptionHandle:
        """Start a new subscription against the provider's own plan id
        (Plan.provider_plan_id). notes carries our own team_id/plan_id so
        the webhook handler can identify what a later event is about."""
        ...

    @abstractmethod
    def create_one_time_order(self, amount: int, currency: str, notes: dict[str, str]) -> OrderHandle:
        """One-off charge (a credit top-up) — amount in the smallest
        currency unit (paise for INR)."""
        ...

    @abstractmethod
    def cancel_subscription(self, provider_subscription_id: str) -> None:
        """Cancel at the end of the current billing period, not instantly —
        the team keeps what they already paid for (see billing_controller.py).
        Raises PaymentProviderError if the provider itself refuses — that
        message is more useful to a user than anything we'd invent."""
        ...

    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """True if this request genuinely came from the provider. Checked
        BEFORE any event is processed — see routes/billing_routes.py."""
        ...

    @abstractmethod
    def verify_order_payment(self, order_id: str, payment_id: str, signature: str) -> bool:
        """Client-side confirmation path (billing_controller.confirm_payment)
        — verifies a one-time-order payment WITHOUT needing a webhook to
        have been delivered. A legitimate, provider-documented verification
        method (a different signature scheme than the webhook's), not a
        workaround — genuinely useful even with webhooks configured, as an
        instant-confirmation path that doesn't wait on webhook delivery."""
        ...

    @abstractmethod
    def verify_subscription_payment(self, subscription_id: str, payment_id: str, signature: str) -> bool:
        """Same idea as verify_order_payment, for a subscription's first
        authorization payment."""
        ...

    @abstractmethod
    def fetch_order(self, order_id: str) -> dict[str, Any]:
        """The order's own record — read back to recover the `notes` set at
        creation time (team_id, credit_pack_id, credit_amount), since the
        client-confirmation callback only hands us ids and a signature."""
        ...

    @abstractmethod
    def fetch_subscription(self, subscription_id: str) -> dict[str, Any]:
        """Same idea as fetch_order, for a subscription's notes (team_id, plan_id).
        NOTE: a subscription entity carries no amount/currency field at
        all — fetch_payment is what has the real charged amount."""
        ...

    @abstractmethod
    def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        """The payment's own record — amount/currency actually charged.
        Needed for confirm_payment's subscription path specifically: a
        subscription entity has no amount field, only the payment does."""
        ...


class RazorpayProvider(PaymentProvider):
    def __init__(self) -> None:
        self._client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

    def create_subscription(self, provider_plan_id: str, notes: dict[str, str]) -> SubscriptionHandle:
        sub = self._client.subscription.create({
            "plan_id": provider_plan_id,
            "customer_notify": 1,
            "total_count": 120,  # effectively "until cancelled" — 10 years
            # of billing cycles; Razorpay subscriptions require SOME finite
            # count, this is the standard workaround for "no fixed end".
            "notes": notes,
        })
        return SubscriptionHandle(
            provider="razorpay",
            provider_subscription_id=sub["id"],
            checkout={"key_id": settings.RAZORPAY_KEY_ID, "subscription_id": sub["id"]},
        )

    def create_one_time_order(self, amount: int, currency: str, notes: dict[str, str]) -> OrderHandle:
        order = self._client.order.create({
            "amount": amount,
            "currency": currency,
            "payment_capture": 1,
            "notes": notes,
        })
        return OrderHandle(
            provider="razorpay",
            provider_order_id=order["id"],
            checkout={"key_id": settings.RAZORPAY_KEY_ID, "order_id": order["id"], "amount": amount, "currency": currency},
        )

    def cancel_subscription(self, provider_subscription_id: str) -> None:
        try:
            self._client.subscription.cancel(provider_subscription_id, data={"cancel_at_cycle_end": 1})
        except razorpay.errors.BadRequestError as exc:
            # e.g. "Subscription cannot be cancelled since no billing cycle
            # is going on" — a subscription that was never actually
            # authorized/paid through a real Razorpay checkout has no
            # server-side billing cycle for Razorpay to defer to, so
            # cancel_at_cycle_end has nothing to act on. Retry immediately
            # (cancel_at_cycle_end=0) rather than surface this as a crash —
            # for a subscription in this state, immediate and end-of-cycle
            # cancellation are the same thing anyway (nothing was ever billed).
            try:
                self._client.subscription.cancel(provider_subscription_id, data={"cancel_at_cycle_end": 0})
            except razorpay.errors.BadRequestError as exc2:
                raise PaymentProviderError(str(exc2)) from exc2

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        try:
            self._client.utility.verify_webhook_signature(
                payload.decode(), signature, settings.RAZORPAY_WEBHOOK_SECRET
            )
            return True
        except razorpay.errors.SignatureVerificationError:
            return False

    def verify_order_payment(self, order_id: str, payment_id: str, signature: str) -> bool:
        try:
            return self._client.utility.verify_payment_signature({
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            })
        except razorpay.errors.SignatureVerificationError:
            return False

    def verify_subscription_payment(self, subscription_id: str, payment_id: str, signature: str) -> bool:
        try:
            return self._client.utility.verify_subscription_payment_signature({
                "razorpay_subscription_id": subscription_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            })
        except razorpay.errors.SignatureVerificationError:
            return False

    def fetch_order(self, order_id: str) -> dict[str, Any]:
        return self._client.order.fetch(order_id)

    def fetch_subscription(self, subscription_id: str) -> dict[str, Any]:
        return self._client.subscription.fetch(subscription_id)

    def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        return self._client.payment.fetch(payment_id)


# The one line every caller goes through. Swap for a different provider
# later; nothing else in the app changes.
payment_provider: PaymentProvider = RazorpayProvider()
