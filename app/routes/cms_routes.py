"""HTTP layer for the CMS — thin wrappers around app/controllers/
cms_controller.py, all behind get_current_admin except /cms/login itself.
Kept entirely separate from the existing app/routes/admin_routes.py: that
one is dev-only ops endpoints (ENV check only); this is a real, permanent
control panel behind a real password.
"""

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.controllers import cms_controller
from app.core.config import settings
from app.core.db import get_db
from app.core.security import create_cms_token
from app.middleware.cms_auth import CMS_COOKIE_NAME, get_current_admin

router = APIRouter(prefix="/cms", tags=["cms"])


@router.post("/login")
def login(password: str = Body(embed=True)):
    if not cms_controller.verify_admin_password(password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong password")
    response = JSONResponse({"message": "Logged in"})
    response.set_cookie(
        key=CMS_COOKIE_NAME,
        value=create_cms_token(),
        httponly=True,
        secure=settings.ENV != "development",
        samesite="lax",
        max_age=settings.CMS_SESSION_MAX_AGE_SECONDS,
    )
    return response


@router.post("/logout")
def logout():
    response = JSONResponse({"message": "Logged out"})
    response.delete_cookie(CMS_COOKIE_NAME)
    return response


@router.get("/me")
def me(_: None = Depends(get_current_admin)):
    return {"authenticated": True}


@router.get("/entities")
def list_entity_configs(_: None = Depends(get_current_admin)):
    return cms_controller.describe_entities()


@router.get("/stats")
def stats(_: None = Depends(get_current_admin), db: Session = Depends(get_db)):
    return cms_controller.get_stats(db)


@router.get("/entities/{entity}")
def list_rows(
    entity: str,
    page: int = Query(1, ge=1),
    search: str | None = None,
    _: None = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    config = cms_controller.get_entity_config(entity)
    return cms_controller.list_rows(db, config, page, search)


@router.post("/entities/{entity}")
def create_row(
    entity: str,
    payload: dict = Body(...),
    _: None = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    config = cms_controller.get_entity_config(entity)
    return cms_controller.create_row(db, config, payload)


@router.get("/entities/{entity}/{row_id}")
def get_row(
    entity: str,
    row_id: str,
    _: None = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    config = cms_controller.get_entity_config(entity)
    return cms_controller.get_row(db, config, row_id)


@router.patch("/entities/{entity}/{row_id}")
def update_row(
    entity: str,
    row_id: str,
    payload: dict = Body(...),
    _: None = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    config = cms_controller.get_entity_config(entity)
    return cms_controller.update_row(db, config, row_id, payload)


@router.delete("/entities/{entity}/{row_id}")
def delete_row(
    entity: str,
    row_id: str,
    _: None = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    config = cms_controller.get_entity_config(entity)
    return cms_controller.delete_row(db, config, row_id)
