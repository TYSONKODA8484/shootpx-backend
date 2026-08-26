from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers import template_controller
from app.core.db import get_db
from app.schemas.templates import TemplateListOut

router = APIRouter(tags=["templates"])


@router.get("/templates", response_model=TemplateListOut)
def list_templates(
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=20, le=100, gt=0),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return template_controller.list_templates(db, category=category, q=q, limit=limit, offset=offset)
