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
    emailed magic link. We verify it, upsert the user, accept ONE specific
    team invite if invite_id was passed (see SessionCreate's docstring —
    never a blanket sweep of everything pending for this email), and set
    our own session cookie.

    A brand-new user still always gets their own personal team
    (create_personal_team) regardless of whether they also happen to be
    accepting an invite in this same call — those are independent: signing
    up via an invite link doesn't mean skipping your own workspace.

    invite_accepted on the response is how the frontend tells "you joined
    the team" apart from "that invite link didn't work" — comparing team
    counts isn't a valid signal since every user always has >=1 team (their
    own personal workspace), so accept_invite's real True/False outcome
    has to ride back on this response instead. Left out of the payload
    entirely (None) when invite_id wasn't sent at all — an ordinary sign-in
    has nothing to report here."""
    decoded = verify_id_token(payload.id_token)
    user, is_new = auth_controller.upsert_user_from_firebase(db, decoded)
    if is_new:
        team_controller.create_personal_team(db, user)

    invite_accepted = None
    if payload.invite_id:
        accepted = team_controller.accept_invite(db, user, payload.invite_id)
        invite_accepted = accepted is not None

    body = UserOut.model_validate(user).model_dump()
    body["invite_accepted"] = invite_accepted
    response = JSONResponse(body)
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
