from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.controllers import billing_controller
from app.core.db import get_db
from app.core.payment_provider import payment_provider
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.billing import (
    BillingConfigOut, CancelRequest, ConfirmPaymentRequest, CreditPackOut, CreditUsageByMemberOut,
    PlanOut, SubscribeRequest, TopupRequest,
)

router = APIRouter(tags=["billing"])


@router.get("/billing/config", response_model=BillingConfigOut)
def get_billing_config(db: Session = Depends(get_db)):
    """Call this before rendering the pricing page — hide the Subscription
    tab entirely when subscriptions_enabled is false (same for
    credits_enabled/Credits tab). Public, no auth needed: this is UI
    configuration, not account data."""
    return billing_controller.get_billing_config(db)


@router.get("/plans", response_model=list[PlanOut])
def list_plans(region: str | None = None, db: Session = Depends(get_db)):
    """region is optional and frontend-supplied (see core/geo_pricing.py's
    docstring for why this isn't GeoIP-guessed server-side) — e.g.
    GET /plans?region=US. Omitted entirely, this returns every plan
    (all regions mixed) for back-compat with any caller that doesn't yet
    send one."""
    return billing_controller.list_plans(db, region)


@router.get("/billing/credit-packs", response_model=list[CreditPackOut])
def list_credit_packs(region: str | None = None, db: Session = Depends(get_db)):
    return billing_controller.list_credit_packs(db, region)


@router.post("/billing/subscribe", status_code=status.HTTP_201_CREATED)
def subscribe(
    payload: SubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return billing_controller.create_subscription(db, current_user, payload.team_id, payload.plan_id)


@router.post("/billing/cancel")
def cancel(
    payload: CancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return billing_controller.cancel_subscription(db, current_user, payload.team_id)


@router.post("/billing/topup", status_code=status.HTTP_201_CREATED)
def topup(
    payload: TopupRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return billing_controller.create_topup_order(db, current_user, payload.team_id, payload.credit_pack_id)


@router.post("/billing/confirm-payment")
def confirm_payment(
    payload: ConfirmPaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Called immediately after Razorpay Checkout's own success handler
    fires — verifies and credits the payment without waiting on (or
    requiring) a webhook. See billing_controller.confirm_payment's
    docstring for why this exists alongside, not instead of, the webhook."""
    return billing_controller.confirm_payment(db, current_user, payload.model_dump())


@router.get("/billing/teams/{team_id}")
def get_billing_status(
    team_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return billing_controller.get_billing_status(db, current_user, team_id)


@router.get("/billing/teams/{team_id}/credit-usage", response_model=CreditUsageByMemberOut)
def get_credit_usage_by_member(
    team_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Owner-only — see billing_controller.get_credit_usage_by_member's
    docstring for exactly which spend this covers."""
    return billing_controller.get_credit_usage_by_member(db, current_user, team_id)


@router.post("/billing/webhook/{provider}")
async def webhook(provider: str, request: Request, db: Session = Depends(get_db)):
    """No session cookie — the provider calls this directly. Signature
    verified against the RAW body before the payload is trusted at all."""
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not payment_provider.verify_webhook_signature(raw_body, signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event", "")
    return billing_controller.process_webhook_event(db, provider, event, payload)
