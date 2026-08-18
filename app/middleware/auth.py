"""The auth guard. Any route that shouldn't be public depends on
`get_current_user` — FastAPI runs it before the route body, so a bad/missing
cookie never reaches your logic at all."""

from datetime import datetime
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core import cache
from app.core.config import settings
from app.core.db import get_db
from app.core.security import read_session_token
from app.models.user import User

COOKIE_NAME = "session_token"
CACHE_NAMESPACE = "login"


def _to_cache(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "created_at": user.created_at.isoformat(),
    }


def _from_cache(data: dict[str, Any]) -> User:
    # A transient (never-queried, session-less) instance — fine here since
    # every caller only reads plain columns off current_user (grep says
    # so: always .id, or the whole object handed straight to a Pydantic
    # response model that only reads columns too). Never touch
    # current_user.memberships on an instance built this way — that
    # relationship was never loaded and there's no Session to lazy-load it
    # from; it'll raise.
    return User(
        id=data["id"],
        email=data["email"],
        name=data["name"],
        avatar_url=data["avatar_url"],
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    user_id = read_session_token(token) if token else None
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    cached = cache.get(CACHE_NAMESPACE, user_id)
    if cached is not None:
        return _from_cache(cached)

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    cache.set(CACHE_NAMESPACE, user_id, _to_cache(user), ttl_seconds=settings.LOGIN_CACHE_TTL_SECONDS)
    return user
