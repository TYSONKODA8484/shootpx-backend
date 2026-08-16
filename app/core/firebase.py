"""Firebase Admin SDK setup. This is what lets the backend verify a token
that Firebase's client SDK handed the frontend after Google sign-in or an
email-link sign-in — we never see the user's Google account or email
provider directly, only Firebase's verdict on who they are.
"""

import os

import firebase_admin
from fastapi import HTTPException, status
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

from app.core.config import settings

_app = None


def init_firebase() -> None:
    """Called once at startup. Tolerates a missing key file so the rest of
    the API (health check, etc.) still boots — login itself will just 500
    with a clear message until the key is in place."""
    global _app
    if _app is not None:
        return
    if not os.path.exists(settings.FIREBASE_SERVICE_ACCOUNT_PATH):
        print(
            f"[firebase] No service-account key at "
            f"{settings.FIREBASE_SERVICE_ACCOUNT_PATH!r} — login is disabled until it's added."
        )
        return
    cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
    _app = firebase_admin.initialize_app(cred)


def generate_email_sign_in_link(email: str, continue_url: str) -> str:
    """Ask Firebase to mint a one-time sign-in link, without asking it to
    email it — we send it ourselves (see controllers/auth_controller.py) so
    it comes from our own address instead of the shared, spam-flagged
    `noreply@<project>.firebaseapp.com`."""
    if _app is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firebase isn't configured on the server yet (missing service-account key).",
        )
    action_code_settings = firebase_auth.ActionCodeSettings(url=continue_url, handle_code_in_app=True)
    return firebase_auth.generate_sign_in_with_email_link(email, action_code_settings)


def verify_id_token(id_token: str) -> dict:
    """Verify a Firebase ID token from the frontend and return its decoded
    claims (uid, email, name, picture, ...). Raises 401 if it's invalid,
    expired, or wasn't actually issued by our Firebase project."""
    if _app is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firebase isn't configured on the server yet (missing service-account key).",
        )
    try:
        return firebase_auth.verify_id_token(id_token)
    except Exception as exc:  # firebase_admin raises several distinct error types
        # The client only ever sees the generic 401 below — but print the
        # real reason server-side, since "invalid token" covers everything
        # from "actually expired" to "clock skew" to "wrong project" and
        # they need very different fixes.
        print(f"[firebase] verify_id_token failed: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired login token"
        ) from exc
