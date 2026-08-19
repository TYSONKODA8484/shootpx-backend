"""Billing logic — subscriptions, top-ups, and the webhook handler that
keeps them honest. See BOOK.md Chapter 17 for the full design reasoning;
this is the implementation of docs/superpowers/specs/2026-08-19-billing-
credits-and-payments-design.md.
"""

from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.credits import add_one_month, apply_credit_delta, get_balance
from app.core.payment_provider import PaymentProviderError, payment_provider
from app.core.permissions import compute_permissions, get_membership
from app.models.credit import CreditPack, CreditReason, CreditTransaction
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.models.plan import BillingCycle, Plan
from app.models.subscription import SubscriptionStatus, TeamSubscription
from app.models.team import Team, new_id
from app.models.user import User


def list_plans(db: Session) -> list[Plan]:
    return db.query(Plan).filter(Plan.is_active == True).all()  # noqa: E712


def list_credit_packs(db: Session) -> list[CreditPack]:
    return db.query(CreditPack).filter(CreditPack.is_active == True).all()  # noqa: E712


def get_free_plan(db: Session) -> Plan:
    plan = db.query(Plan).filter(Plan.billing_cycle == BillingCycle.free.value, Plan.is_active == True).first()  # noqa: E712
    if plan is None:
        raise RuntimeError("No Free plan seeded — run migrations (see alembic/versions for the seed migration)")
    return plan


def assign_free_plan(db: Session, team: Team) -> TeamSubscription:
    """Called once, right when a team is created (team_controller.
    create_personal_team) — grants the Free plan's starter credits
    SYNCHRONOUSLY, not via the refill cron. A brand-new signup must never
    wait on a daily cron tick for its first credits; see core/credits.py's
    module docstring and BOOK.md Chapter 17's "why the cost is locked in"
    discussion of the same principle applied to grants."""
    plan = get_free_plan(db)
    sub = TeamSubscription(
        team_id=team.id,
        plan_id=plan.id,
        status=SubscriptionStatus.free.value,
        next_credit_refill_at=add_one_month(datetime.utcnow()),
    )
    db.add(sub)
    db.flush()
    apply_credit_delta(db, team.id, plan.credit_allowance, reason=CreditReason.plan_grant.value)
    db.commit()
    return sub


def get_billing_status(db: Session, current_user: User, team_id: str) -> dict:
    get_membership(db, team_id, current_user.id)
    sub = db.query(TeamSubscription).filter(TeamSubscription.team_id == team_id).first()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No subscription found for this team")
    plan = db.get(Plan, sub.plan_id)
    balance = get_balance(db, team_id)
    recent = (
        db.query(CreditTransaction)
        .filter(CreditTransaction.team_id == team_id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "team_id": team_id,
        "plan": plan,
        "subscription_status": sub.status,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        "balance": balance,
        "recent_transactions": [
            {
                "amount": t.amount, "reason": t.reason, "reference_id": t.reference_id,
                "balance_after": t.balance_after, "created_at": t.created_at.isoformat(),
            }
            for t in recent
        ],
    }


def create_subscription(db: Session, current_user: User, team_id: str, plan_id: str) -> dict:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_manage_team:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the team owner can manage billing")

    plan = db.get(Plan, plan_id)
    if plan is None or not plan.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown or inactive plan")

    sub = db.query(TeamSubscription).filter(TeamSubscription.team_id == team_id).first()

    if sub is not None and sub.status == SubscriptionStatus.active.value:
        # Already on an active paid plan -> this is a PLAN CHANGE, not a
        # fresh subscription. Takes effect at next renewal, no proration
        # (deliberately deferred — see the spec's non-goals).
        sub.plan_id = plan.id
        db.commit()
        return {"kind": "plan_change", "effective": "next_renewal", "plan_id": plan.id}

    if plan.billing_cycle == BillingCycle.free.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot 'subscribe' to the Free plan directly — it's the default")

    handle = payment_provider.create_subscription(
        provider_plan_id=plan.provider_plan_id,
        notes={"team_id": team_id, "plan_id": plan.id},
    )

    if sub is None:
        sub = TeamSubscription(
            team_id=team_id, plan_id=plan.id,
            status=SubscriptionStatus.past_due.value,  # pending until the
            # activation webhook confirms it — "past_due" reused rather
            # than adding a new enum value purely for "awaiting first
            # payment"; both mean "not currently granting access".
            next_credit_refill_at=add_one_month(datetime.utcnow()),
        )
        db.add(sub)
    sub.plan_id = plan.id
    sub.provider = handle.provider
    sub.provider_subscription_id = handle.provider_subscription_id
    db.commit()

    return {"kind": "new_subscription", "provider": handle.provider, "checkout": handle.checkout}


def cancel_subscription(db: Session, current_user: User, team_id: str) -> dict:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_manage_team:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the team owner can manage billing")

    sub = db.query(TeamSubscription).filter(TeamSubscription.team_id == team_id).first()
    if sub is None or not sub.provider_subscription_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No active paid subscription to cancel")

    try:
        payment_provider.cancel_subscription(sub.provider_subscription_id)
    except PaymentProviderError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not cancel: {exc}") from exc
    # Does NOT downgrade immediately — the team keeps what they already
    # paid for until current_period_end. The webhook (subscription.cancelled)
    # confirms the provider-side cancellation; actually moving to Free
    # happens the same way a halted subscription does (see process_webhook_event).
    sub.status = SubscriptionStatus.cancelled.value
    db.commit()
    return {"status": "cancelled", "effective": sub.current_period_end.isoformat() if sub.current_period_end else "end of current period"}


def create_topup_order(db: Session, current_user: User, team_id: str, credit_pack_id: str) -> dict:
    get_membership(db, team_id, current_user.id)
    pack = db.get(CreditPack, credit_pack_id)
    if pack is None or not pack.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown or inactive credit pack")

    handle = payment_provider.create_one_time_order(
        amount=pack.price, currency=pack.currency,
        notes={"team_id": team_id, "credit_pack_id": pack.id, "credit_amount": str(pack.credit_amount)},
    )
    return {"provider": handle.provider, "checkout": handle.checkout}


def _downgrade_to_free(db: Session, team_id: str) -> None:
    sub = db.query(TeamSubscription).filter(TeamSubscription.team_id == team_id).first()
    if sub is None:
        return
    free_plan = get_free_plan(db)
    sub.plan_id = free_plan.id
    sub.status = SubscriptionStatus.free.value
    sub.provider = None
    sub.provider_subscription_id = None
    sub.current_period_end = None
    db.commit()


def process_webhook_event(db: Session, provider: str, event: str, payload: dict) -> dict:
    """Idempotent: checks `payments` for the event's own payment id BEFORE
    granting anything or changing state — providers redeliver webhook
    events at-least-once, never exactly-once."""
    entity = payload.get("payload", {})

    if event in ("subscription.activated", "subscription.charged"):
        sub_entity = entity.get("subscription", {}).get("entity", {})
        payment_entity = entity.get("payment", {}).get("entity", {})
        provider_subscription_id = sub_entity.get("id")
        provider_payment_id = payment_entity.get("id")

        if provider_payment_id and db.query(Payment).filter(Payment.provider_payment_id == provider_payment_id).first():
            return {"status": "already_processed"}  # idempotency guard

        sub = db.query(TeamSubscription).filter(TeamSubscription.provider_subscription_id == provider_subscription_id).first()
        if sub is None:
            return {"status": "unknown_subscription"}

        is_first_charge = sub.current_period_end is None
        sub.status = SubscriptionStatus.active.value
        sub.current_period_end = datetime.utcnow() + timedelta(days=30)

        if provider_payment_id:
            db.add(Payment(
                team_id=sub.team_id, provider=provider, provider_payment_id=provider_payment_id,
                provider_subscription_id=provider_subscription_id,
                amount=payment_entity.get("amount", 0), currency=payment_entity.get("currency", "INR"),
                status=PaymentStatus.captured.value, kind=PaymentKind.subscription_charge.value,
            ))

        if is_first_charge:
            # Synchronous grant for the FIRST charge only — every
            # subsequent cycle (monthly or yearly) is granted by the
            # refill cron instead, never by this webhook, so the two
            # mechanisms never double-grant the same month.
            plan = db.get(Plan, sub.plan_id)
            apply_credit_delta(db, sub.team_id, plan.credit_allowance, reason=CreditReason.plan_grant.value, reference_id=provider_payment_id)
            sub.next_credit_refill_at = add_one_month(datetime.utcnow())

        db.commit()
        return {"status": "processed"}

    if event == "subscription.cancelled":
        sub_entity = entity.get("subscription", {}).get("entity", {})
        sub = db.query(TeamSubscription).filter(TeamSubscription.provider_subscription_id == sub_entity.get("id")).first()
        if sub:
            sub.status = SubscriptionStatus.cancelled.value
            db.commit()
        return {"status": "processed"}

    if event == "subscription.halted":
        sub_entity = entity.get("subscription", {}).get("entity", {})
        sub = db.query(TeamSubscription).filter(TeamSubscription.provider_subscription_id == sub_entity.get("id")).first()
        if sub:
            _downgrade_to_free(db, sub.team_id)
        return {"status": "processed"}

    if event == "payment.captured":
        # A ONE-TIME order (top-up) succeeding — subscription charges are
        # handled entirely by the subscription.activated/charged branch
        # above, never here. Identified by `notes.credit_pack_id`, which
        # create_topup_order always sets on the order/payment at creation
        # time — Razorpay round-trips notes back on the payment entity, so
        # no local "pending order" row is needed to recover team_id/amount.
        payment_entity = entity.get("payment", {}).get("entity", {})
        notes = payment_entity.get("notes") or {}
        if "credit_pack_id" not in notes:
            return {"status": "ignored", "reason": "not a top-up payment"}

        provider_payment_id = payment_entity.get("id")
        if provider_payment_id and db.query(Payment).filter(Payment.provider_payment_id == provider_payment_id).first():
            return {"status": "already_processed"}

        team_id = notes.get("team_id")
        credit_amount = int(notes.get("credit_amount", 0))

        db.add(Payment(
            team_id=team_id, provider=provider, provider_payment_id=provider_payment_id,
            provider_order_id=payment_entity.get("order_id"),
            amount=payment_entity.get("amount", 0), currency=payment_entity.get("currency", "INR"),
            status=PaymentStatus.captured.value, kind=PaymentKind.topup.value,
        ))
        apply_credit_delta(db, team_id, credit_amount, reason=CreditReason.topup_purchase.value, reference_id=provider_payment_id)
        db.commit()
        return {"status": "processed"}

    if event == "payment.failed":
        return {"status": "acknowledged"}  # subscription.halted (Razorpay's
        # own dunning conclusion) is what actually triggers the downgrade;
        # a single failed payment is expected to retry automatically.

    if event == "refund.processed":
        payment_entity = entity.get("payment", {}).get("entity", {})
        provider_payment_id = payment_entity.get("id")
        pay_row = db.query(Payment).filter(Payment.provider_payment_id == provider_payment_id).first()
        if pay_row is None:
            return {"status": "unknown_payment"}
        if db.query(CreditTransaction).filter(
            CreditTransaction.reference_id == provider_payment_id, CreditTransaction.reason == CreditReason.refund.value
        ).first():
            return {"status": "already_processed"}  # idempotency guard,
            # separate from the payments-table check above since a refund
            # is a SECOND event against an already-recorded payment id.
        pay_row.status = PaymentStatus.refunded.value
        balance = get_balance(db, pay_row.team_id)
        db.add(CreditTransaction(
            id=new_id(), team_id=pay_row.team_id, amount=0, reason=CreditReason.refund.value,
            reference_id=provider_payment_id, balance_after=balance,
        ))
        # Does NOT claw back credits already spent — only the ledger
        # reflects the money movement. amount=0 deliberately: this is a
        # record of a refund happening, not a credit adjustment.
        db.commit()
        return {"status": "processed"}

    return {"status": "ignored", "event": event}
