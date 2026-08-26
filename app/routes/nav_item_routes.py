from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import nav_item_controller
from app.core.db import get_db
from app.schemas.nav_items import NavItemOut

router = APIRouter(tags=["nav-items"])


@router.get("/nav-items", response_model=list[NavItemOut])
def list_nav_items(db: Session = Depends(get_db)):
    return nav_item_controller.list_nav_items(db)
