"""The CMS's own auth guard — separate from the regular user session
(app/middleware/auth.py). A single shared password protects the whole CMS,
not a per-user role, since there's no admin-role concept anywhere in this
app."""

from fastapi import HTTPException, Request, status

from app.core.security import read_cms_token

CMS_COOKIE_NAME = "cms_session"


def get_current_admin(request: Request) -> None:
    token = request.cookies.get(CMS_COOKIE_NAME)
    if not token or not read_cms_token(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
