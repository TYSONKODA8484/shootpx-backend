from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.controllers import billing_controller
from app.core.db import get_db
from app.core.payment_provider import payment_provider
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.billing import CancelRequest, CreditPackOut, PlanOut, SubscribeRequest, TopupRequest

router = APIRouter(tags=["billing"])


@router.get("/plans", response_model=list[PlanOut])
def list_plans(db: Session = Depends(get_db)):
    return billing_controller.list_plans(db)


@router.get("/billing/credit-packs", response_model=list[CreditPackOut])
def list_credit_packs(db: Session = Depends(get_db)):
    return billing_controller.list_credit_packs(db)


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


@router.get("/billing/teams/{team_id}")
def get_billing_status(
    team_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return billing_controller.get_billing_status(db, current_user, team_id)


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
