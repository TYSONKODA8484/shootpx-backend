"""Billing logic — subscriptions, top-ups, and the webhook handler that
keeps them honest. See BOOK.md Chapter 17 for the full design reasoning;
this is the implementation of docs/superpowers/specs/2026-08-19-billing-
credits-and-payments-design.md.
"""

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.credits import add_refill_interval, apply_credit_delta, get_balance, period_length
from app.core.geo_pricing import normalize_region
from app.core.payment_provider import PaymentProviderError, payment_provider
from app.core.permissions import compute_permissions, get_membership
from app.core.time import utc_now
from app.models.billing_mode import BillingMode
from app.models.credit import CreditPack, CreditReason, CreditTransaction
from app.models.generation_job import GenerationJob
from app.models.payment import Payment, PaymentKind, PaymentStatus
from app.models.plan import BillingCycle, Plan
from app.models.subscription import SubscriptionStatus, TeamSubscription
from app.models.team import Team, new_id
from app.models.user import User


def get_billing_config(db: Session) -> dict:
    """Backs GET /billing/config — see BillingMode's docstring. Defaults an
    UNSEEDED mode to enabled (True) rather than hiding it: a row missing
    entirely (migration not yet run, or a fresh dev DB) should never look
    like a deliberate admin decision to turn something off — only an
    explicit is_active=false row does that."""
    rows = {m.key: m.is_active for m in db.query(BillingMode).all()}
    return {
        "subscriptions_enabled": rows.get("subscriptions", True),
        "credits_enabled": rows.get("credits", True),
    }


def list_plans(db: Session, region: str | None = None) -> list[Plan]:
    """With no region given, returns every active plan (Free plus every
    region's paid variants) — the pre-geo-pricing behavior, still used by
    anything that doesn't care about region (e.g. looking up a specific
    plan_id later). Pass a region to get what a signup should actually be
    OFFERED: the Free plan (region-less, shown everywhere) plus only that
    region's paid variants, never a mix of currencies in one list."""
    query = db.query(Plan).filter(Plan.is_active == True)  # noqa: E712
    if region is None:
        return query.all()
    resolved = normalize_region(region)
    return query.filter((Plan.region == resolved) | (Plan.region.is_(None))).all()


def list_credit_packs(db: Session, region: str | None = None) -> list[CreditPack]:
    """Same region-filtering shape as list_plans — see that docstring."""
    query = db.query(CreditPack).filter(CreditPack.is_active == True)  # noqa: E712
    if region is None:
        return query.all()
    resolved = normalize_region(region)
    return query.filter((CreditPack.region == resolved) | (CreditPack.region.is_(None))).all()


def get_billing_catalog(db: Session, region: str | None = None) -> dict:
    """Backs GET /billing/catalog — everything a pricing page needs in one
    round trip: which tabs are even offered (same data as GET
    /billing/config) plus every plan and credit pack available to buy
    right now (same data as GET /plans + GET /billing/credit-packs). Those
    three endpoints still exist and still work unchanged for any other
    caller, but a pricing page should call this instead of all three.
    Same region behavior as list_plans/list_credit_packs — pass region to
    get only that region's paid variants alongside the region-less rows
    (Free plan, any pack priced the same everywhere), omit for everything
    mixed."""
    config = get_billing_config(db)
    return {
        **config,
        "plans": list_plans(db, region),
        "credit_packs": list_credit_packs(db, region),
    }


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
        next_credit_refill_at=add_refill_interval(utc_now(), plan.billing_cycle),
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


def get_credit_usage_by_member(db: Session, current_user: User, team_id: str) -> dict:
    """Backs GET /billing/teams/{team_id}/credit-usage — owner-only (this
    is a management report, not something every teammate needs to see).

    Only covers CreditReason.generation_spend: that's the only spend
    reason whose reference_id (a GenerationJob id) reliably identifies WHO
    caused it (GenerationJob.created_by). export_spend's reference_id is
    the source asset id, whose created_by is whoever made that asset
    originally — not necessarily whoever clicked Export — so attributing
    it per-user here would misattribute the spend; deliberately excluded
    rather than shown wrong. plan_grant/topup_purchase/refund/
    manual_adjustment/subscription_cancelled are team-level events with no
    single "user who did this" to attribute to."""
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_manage_team:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the team owner can view credit usage by member")

    rows = (
        db.query(GenerationJob.created_by, func.sum(CreditTransaction.amount))
        .join(GenerationJob, GenerationJob.id == CreditTransaction.reference_id)
        .filter(
            CreditTransaction.team_id == team_id,
            CreditTransaction.reason == CreditReason.generation_spend.value,
        )
        .group_by(GenerationJob.created_by)
        .all()
    )

    user_ids = [user_id for user_id, _ in rows]
    users_by_id = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    by_member = [
        {
            "user_id": user_id,
            "email": users_by_id[user_id].email if user_id in users_by_id else None,
            "name": users_by_id[user_id].name if user_id in users_by_id else None,
            "credits_spent": -total,  # CreditTransaction.amount is signed negative for a spend
        }
        for user_id, total in rows
    ]
    by_member.sort(key=lambda m: m["credits_spent"], reverse=True)

    return {
        "team_id": team_id,
        "total_credits_spent": sum(m["credits_spent"] for m in by_member),
        "by_member": by_member,
    }


def _find_plan(db: Session, plan_id: str) -> Plan | None:
    """plan_id may be EITHER our internal plans.id (a UUID) OR a paid
    plan's provider_plan_id (Razorpay's own id, e.g. "plan_TV6uz...") —
    the frontend is meant to treat provider_plan_id as a paid plan's real
    identifier (see Plan's docstring), so every plan-accepting endpoint
    needs to resolve either form rather than force callers to first look
    up our internal id. Checked by primary key first since that's an
    indexed point lookup; provider_plan_id has no unique constraint of its
    own today but is expected to be unique in practice (one Razorpay plan
    backs at most one row)."""
    plan = db.get(Plan, plan_id)
    if plan is not None:
        return plan
    return db.query(Plan).filter(Plan.provider_plan_id == plan_id).first()


def create_subscription(db: Session, current_user: User, team_id: str, plan_id: str) -> dict:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_manage_team:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the team owner can manage billing")

    plan = _find_plan(db, plan_id)
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
            next_credit_refill_at=add_refill_interval(utc_now(), plan.billing_cycle),
        )
        db.add(sub)
    else:
        # Re-subscribing after a cancellation (or any non-active prior
        # state) reuses this team's one TeamSubscription row rather than
        # creating a second one (team_id is unique). A REAL bug lived
        # here: current_period_end was left at whatever the PREVIOUS,
        # now-cancelled subscription's cycle end was, never cleared. The
        # first charge on THIS new subscription would then land in
        # _credit_subscription_charge, which decides "is this the first
        # charge" purely from `current_period_end is None` — with the old
        # value still sitting there, it wrongly concluded "not the first
        # charge" and silently skipped the credit grant entirely. Caught
        # from a real report: a real re-subscribe payment went through,
        # nothing was ever credited. Reset both here, explicitly, for
        # every subscription this row is reused for, not just the first.
        sub.status = SubscriptionStatus.past_due.value
        sub.current_period_end = None
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

    # Razorpay itself stops future billing (no auto-renewal, no further
    # charges — cancel_at_cycle_end on the provider side already guarantees
    # this) and we never refund money. What THIS system controls is the
    # CREDIT balance: cancelling claws back this cycle's still-unused
    # subscription allowance immediately, capped at whatever's actually
    # left — min(balance, plan.credit_allowance), never more. Top-up
    # ("lifetime") credits bought separately are never touched, because
    # this is a flat cap on the clawback amount, not a search through which
    # credits came from where — the two examples that define this rule:
    # 101 left (100 from the plan + 1 leftover top-up) -> claw back 100,
    # 1 remains; 94 left (all plan-granted, nothing bought separately) ->
    # claw back 94 (capped, not the full 100), 0 remains. See BOOK.md
    # Chapter 17.
    plan = db.get(Plan, sub.plan_id)
    if plan is not None:
        balance = get_balance(db, team_id)
        clawback = min(balance, plan.credit_allowance)
        if clawback > 0:
            apply_credit_delta(
                db, team_id, -clawback, reason=CreditReason.subscription_cancelled.value,
                reference_id=sub.provider_subscription_id,
            )

    # Does NOT downgrade the PLAN immediately — the team keeps paid-tier
    # access (e.g. max_team_members) until current_period_end; only the
    # credit balance is adjusted right now. The webhook (subscription.cancelled)
    # confirms the provider-side cancellation; actually moving the plan to
    # Free happens the same way a halted subscription does (see process_webhook_event).
    sub.status = SubscriptionStatus.cancelled.value
    db.commit()
    return {"status": "cancelled", "effective": sub.current_period_end.isoformat() if sub.current_period_end else "end of current period"}


def create_topup_order(db: Session, current_user: User, team_id: str, credit_pack_id: str) -> dict:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_manage_team:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the team owner can buy credits")

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


def _credit_subscription_charge(
    db: Session, provider: str, provider_subscription_id: str, provider_payment_id: str | None,
    amount: int, currency: str,
) -> dict:
    """Shared by BOTH the webhook handler (subscription.activated/charged)
    and confirm_payment (the client-side path, for when no publicly
    reachable webhook URL exists — see BOOK.md Chapter 17's "why webhooks
    alone aren't enough for local dev" discussion). Idempotent: checked
    against `payments` before granting anything, so it's safe for either
    path, or both, to call this for the same payment."""
    if provider_payment_id and db.query(Payment).filter(Payment.provider_payment_id == provider_payment_id).first():
        return {"status": "already_processed"}

    sub = db.query(TeamSubscription).filter(TeamSubscription.provider_subscription_id == provider_subscription_id).first()
    if sub is None:
        return {"status": "unknown_subscription"}

    plan = db.get(Plan, sub.plan_id)
    is_first_charge = sub.current_period_end is None
    sub.status = SubscriptionStatus.active.value
    sub.current_period_end = utc_now() + period_length(plan.billing_cycle if plan else "monthly")

    if provider_payment_id:
        db.add(Payment(
            team_id=sub.team_id, provider=provider, provider_payment_id=provider_payment_id,
            provider_subscription_id=provider_subscription_id,
            amount=amount, currency=currency,
            status=PaymentStatus.captured.value, kind=PaymentKind.subscription_charge.value,
        ))

    if is_first_charge and plan is not None:
        # Synchronous grant for the FIRST charge only — every subsequent
        # cycle (weekly/monthly/yearly) is granted by the refill cron
        # instead, never by this path, so the two mechanisms never
        # double-grant the same period.
        apply_credit_delta(db, sub.team_id, plan.credit_allowance, reason=CreditReason.plan_grant.value, reference_id=provider_payment_id)
        sub.next_credit_refill_at = add_refill_interval(utc_now(), plan.billing_cycle)

    db.commit()
    return {"status": "processed"}


def _credit_topup(
    db: Session, provider: str, provider_payment_id: str, notes: dict, amount: int, currency: str,
) -> dict:
    """Shared by both the webhook handler (payment.captured) and
    confirm_payment. `notes` (team_id/credit_pack_id/credit_amount) is
    whatever create_topup_order attached at order-creation time —
    round-tripped back by Razorpay either on the webhook payload or via a
    fresh fetch_order() call, same data either way."""
    if "credit_pack_id" not in notes:
        return {"status": "ignored", "reason": "not a top-up payment"}

    if provider_payment_id and db.query(Payment).filter(Payment.provider_payment_id == provider_payment_id).first():
        return {"status": "already_processed"}

    team_id = notes.get("team_id")
    credit_amount = int(notes.get("credit_amount", 0))

    db.add(Payment(
        team_id=team_id, provider=provider, provider_payment_id=provider_payment_id,
        provider_order_id=notes.get("order_id"),
        amount=amount, currency=currency,
        status=PaymentStatus.captured.value, kind=PaymentKind.topup.value,
    ))
    apply_credit_delta(db, team_id, credit_amount, reason=CreditReason.topup_purchase.value, reference_id=provider_payment_id)
    db.commit()
    return {"status": "processed"}


def confirm_payment(db: Session, current_user: User, payload: dict) -> dict:
    """The CLIENT-SIDE confirmation path — called by the test console (or a
    real frontend) immediately after Razorpay Checkout's own `handler`
    callback fires, instead of waiting for a webhook. Local dev has no
    publicly reachable URL for Razorpay to deliver a webhook to at all, so
    without this, a real successful payment would silently never credit
    anyone — exactly the bug this was added to fix. Verifies the payment
    itself (a legitimate, provider-documented signature scheme, distinct
    from the webhook's), independent of whether a webhook ever arrives —
    genuinely useful in production too, as an instant-confirmation path
    that doesn't wait on webhook delivery. Idempotency (shared with the
    webhook path via _credit_subscription_charge/_credit_topup) means it's
    safe if both paths end up firing for the same payment."""
    payment_id = payload.get("razorpay_payment_id")
    order_id = payload.get("razorpay_order_id")
    subscription_id = payload.get("razorpay_subscription_id")
    signature = payload.get("razorpay_signature")

    if not payment_id or not signature or (not order_id and not subscription_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing required payment confirmation fields")

    try:
        if subscription_id:
            if not payment_provider.verify_subscription_payment(subscription_id, payment_id, signature):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment signature verification failed")
            sub_entity = payment_provider.fetch_subscription(subscription_id)
            get_membership(db, sub_entity.get("notes", {}).get("team_id", ""), current_user.id)
            # A subscription entity carries NO amount/currency field at all —
            # the real charged amount only exists on the payment itself. The
            # earlier version guessed at a `plan.item.amount` path that
            # doesn't exist in Razorpay's actual response shape, silently
            # recording every subscription payment's amount as 0 — harmless to
            # crediting (which only ever used credit_allowance, not this
            # amount), but wrong for `payments` as an audit/reconciliation
            # record, which is the entire point of that table.
            payment_entity = payment_provider.fetch_payment(payment_id)
            return _credit_subscription_charge(
                db, "razorpay", subscription_id, payment_id,
                amount=payment_entity.get("amount", 0), currency=payment_entity.get("currency", "INR"),
            )

        if not payment_provider.verify_order_payment(order_id, payment_id, signature):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment signature verification failed")
        order_entity = payment_provider.fetch_order(order_id)
        notes = dict(order_entity.get("notes") or {})
        notes["order_id"] = order_id
        get_membership(db, notes.get("team_id", ""), current_user.id)
        return _credit_topup(db, "razorpay", payment_id, notes, amount=order_entity.get("amount", 0), currency=order_entity.get("currency", "INR"))
    except PaymentProviderError as exc:
        # A nonexistent/malformed order_id or subscription_id reaching
        # Razorpay's own fetch — e.g. a stale value, a typo, or someone
        # probing this endpoint with made-up ids. Without this, that would
        # surface as an unhandled 500 (see payment_provider.py's
        # fetch_order/fetch_subscription/fetch_payment) instead of a clean
        # 4xx the frontend can actually show a message for.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not verify payment: {exc}") from exc


def process_webhook_event(db: Session, provider: str, event: str, payload: dict) -> dict:
    """Idempotent: checks `payments` for the event's own payment id BEFORE
    granting anything or changing state — providers redeliver webhook
    events at-least-once, never exactly-once. Same crediting logic as
    confirm_payment (the client-side path) via the shared
    _credit_subscription_charge/_credit_topup helpers — this is the path
    that matters once a real, publicly reachable deployment exists."""
    entity = payload.get("payload", {})

    if event in ("subscription.activated", "subscription.charged"):
        sub_entity = entity.get("subscription", {}).get("entity", {})
        payment_entity = entity.get("payment", {}).get("entity", {})
        return _credit_subscription_charge(
            db, provider, sub_entity.get("id"), payment_entity.get("id"),
            amount=payment_entity.get("amount", 0), currency=payment_entity.get("currency", "INR"),
        )

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
        # above, never here.
        payment_entity = entity.get("payment", {}).get("entity", {})
        notes = dict(payment_entity.get("notes") or {})
        notes.setdefault("order_id", payment_entity.get("order_id"))
        return _credit_topup(
            db, provider, payment_entity.get("id"), notes,
            amount=payment_entity.get("amount", 0), currency=payment_entity.get("currency", "INR"),
        )

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
