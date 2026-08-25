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


# The CMS's own signed token — same itsdangerous mechanism as the user
# session token above, deliberately a different salt so one token type can
# never be mistaken for (or forged from) the other.
_cms_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="cms_session")


def create_cms_token() -> str:
    return _cms_serializer.dumps({"cms_admin": True})


def read_cms_token(token: str) -> bool:
    try:
        data = _cms_serializer.loads(token, max_age=settings.CMS_SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return False
    return bool(data.get("cms_admin"))
