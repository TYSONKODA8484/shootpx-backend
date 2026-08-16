from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.controllers import auth_controller, team_controller
from app.core.db import get_db
from app.core.firebase import verify_id_token
from app.middleware.auth import COOKIE_NAME, get_current_user
from app.models.user import User
from app.schemas.auth import EmailLinkRequest, SessionCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/email-link")
def request_email_link(payload: EmailLinkRequest, background_tasks: BackgroundTasks):
    """Generates the one-time Firebase sign-in link and emails it ourselves
    (via our own SMTP) instead of letting Firebase send it — avoids the
    shared noreply@<project>.firebaseapp.com address landing in spam."""
    background_tasks.add_task(auth_controller.send_email_sign_in_link, payload.email, payload.continue_url)
    return {"message": f"Check {payload.email} for a sign-in link."}


@router.post("/session", response_model=UserOut)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)):
    """The frontend calls this right after Firebase Auth hands it an ID
    token — whether that came from the Google popup or from clicking the
    emailed magic link. We verify it, upsert the user, pull in any pending
    team invites for their email, and set our own session cookie."""
    decoded = verify_id_token(payload.id_token)
    user = auth_controller.upsert_user_from_firebase(db, decoded)
    team_controller.accept_pending_invites(db, user)

    response = JSONResponse(UserOut.model_validate(user).model_dump())
    auth_controller.set_session_cookie(response, user.id)
    return response


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
def logout():
    response = JSONResponse({"message": "Logged out"})
    response.delete_cookie(COOKIE_NAME)
    return response
