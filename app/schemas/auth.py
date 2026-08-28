from pydantic import BaseModel, ConfigDict, EmailStr


class SessionCreate(BaseModel):
    id_token: str  # the Firebase ID token the frontend got from Firebase Auth
    invite_id: str | None = None  # from the invite email link's ?invite_id=
    # query param (see team_controller.send_team_invite_email/accept_invite)
    # — the frontend's auth callback page extracts this from the URL it
    # landed on and passes it through here so /auth/session can accept
    # that SPECIFIC invite. Omitted for an ordinary login/signup.


class EmailLinkRequest(BaseModel):
    email: EmailStr
    continue_url: str  # where the link should land — the page that finishes sign-in


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str | None = None
    avatar_url: str | None = None
    invite_accepted: bool | None = None  # only meaningful on POST /auth/session
    # when the request included invite_id (see SessionCreate). True = that
    # specific invite was found, unexpired, matched this user's email, and
    # just got accepted. False = an invite_id was sent but acceptance
    # failed (expired / already accepted / wrong email / unknown id — one
    # boolean, the frontend doesn't need to distinguish which). Left as
    # None/omitted for an ordinary sign-in with no invite_id at all, and
    # for GET /auth/me (which also returns UserOut but has no invite
    # context to report — see auth_routes.py's create_session vs me).
