"""Signed, tamper-proof session tokens.

Uses itsdangerous rather than JWT: both are signed with SECRET_KEY, both carry
an expiry, and we don't need JWT's cross-service portability here.
"""

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings

_session_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="session")


def create_session_token(user_id: str) -> str:
    return _session_serializer.dumps({"user_id": user_id})


def read_session_token(token: str) -> str | None:
    try:
        data = _session_serializer.loads(token, max_age=settings.SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")
