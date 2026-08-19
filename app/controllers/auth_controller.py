from sqlalchemy.orm import Session

from app.core import cache
from app.core.config import settings
from app.core.email import send_email
from app.core.firebase import generate_email_sign_in_link
from app.core.security import create_session_token
from app.middleware.auth import CACHE_NAMESPACE, COOKIE_NAME
from app.models.user import User


def send_email_sign_in_link(email: str, continue_url: str) -> None:
    link = generate_email_sign_in_link(email, continue_url)
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: auto;">
      <h2>Sign in to {settings.APP_NAME}</h2>
      <p>Click the button below to sign in. This link is single-use and expires soon.</p>
      <p style="margin: 24px 0;">
        <a href="{link}"
           style="background:#111;color:#fff;padding:12px 20px;border-radius:6px;text-decoration:none;">
          Sign in to {settings.APP_NAME}
        </a>
      </p>
      <p>If you didn't request this, you can safely ignore this email.</p>
    </div>
    """
    send_email(email, f"Sign in to {settings.APP_NAME}", html)


def upsert_user_from_firebase(db: Session, decoded_token: dict) -> tuple[User, bool]:
    """users.id is normally the Firebase uid — usually the same uid whether
    someone signs in through Google or an email link for the same address,
    since Firebase's default account-linking merges them.

    But that linking is a *project setting*, not a guarantee, and newer
    Firebase projects default to "one account per identity provider" instead
    — meaning the SAME email can hand back a DIFFERENT uid depending which
    method they used. If we blindly inserted on every unseen uid, that would
    crash on the `users.email` unique constraint the moment someone's second
    sign-in method surfaced a new uid for an email we already have. So: uid
    lookup first, then fall back to an email match — if we find one, that's
    the same person, just re-use their existing row rather than duplicating
    it under a second id.
    """
    uid = decoded_token["uid"]
    email = decoded_token["email"]
    name = decoded_token.get("name")  # optional — fine if not provided
    avatar_url = decoded_token.get("picture")  # optional — fine if not provided

    user = db.get(User, uid)
    if not user:
        user = db.query(User).filter(User.email == email).first()

    # True only when NEITHER lookup above found an existing row — i.e. this
    # is this person's actual first-ever sign-in, not a normal re-login and
    # not the "second sign-in method surfaces a new uid" case handled by the
    # email fallback. auth_routes.py uses this to decide whether to create
    # a personal team — must never fire twice for the same person.
    is_new = user is None

    if user:
        user.email = email
        user.name = user.name or name
        user.avatar_url = user.avatar_url or avatar_url
    else:
        user = User(id=uid, email=email, name=name, avatar_url=avatar_url)
        db.add(user)

    db.commit()
    db.refresh(user)

    # Invalidate rather than wait out LOGIN_CACHE_TTL_SECONDS — this is the
    # one place a User row's cached fields (email/name/avatar_url) can
    # actually change, and it happens right at sign-in, so the very next
    # request (this session) should see the fresh row, not a stale one
    # cached from before this upsert.
    cache.delete(CACHE_NAMESPACE, user.id)

    return user, is_new


def set_session_cookie(response, user_id: str) -> None:
    token = create_session_token(user_id)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.ENV != "development",
        samesite="lax",
        max_age=settings.SESSION_MAX_AGE_SECONDS,
    )
