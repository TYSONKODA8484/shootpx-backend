"""Dev-only operational endpoints — nothing here is meant to ever run in
production. GET /tools is the one exception (public catalog data, same
spirit as /health) and stays available in every environment.
"""

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import cache
from app.core.cache import KNOWN_CACHE_NAMESPACES
from app.core.config import settings
from app.core.db import get_db
from app.models.tool import Tool
from app.schemas.tools import ToolOut

router = APIRouter(tags=["admin"])


@router.post("/admin/cache/clear")
def clear_cache(namespace: str = Body(embed=True)):
    """Exposes core/cache.py's clear_namespace() as a route so it's click-
    able from the test console instead of only callable from a Python
    shell. 404 (not 403) outside development — same "don't even confirm
    this exists" pattern get_membership already uses for team access."""
    if settings.ENV != "development":
        raise HTTPException(status_code=404)

    if namespace == "all":
        total = sum(cache.clear_namespace(ns) for ns in KNOWN_CACHE_NAMESPACES)
        return {"namespace": "all", "cleared": total}

    if namespace not in KNOWN_CACHE_NAMESPACES:
        raise HTTPException(status_code=400, detail=f"Unknown namespace: {namespace!r}")

    return {"namespace": namespace, "cleared": cache.clear_namespace(namespace)}


@router.get("/tools", response_model=list[ToolOut])
def list_tools(db: Session = Depends(get_db)):
    """Every active tool — lets a client discover what's available to pass
    as feature_type before calling /generate, instead of only being able to
    spend against one it already knows. No auth required: this is public
    catalog data, not team-scoped."""
    return db.query(Tool).filter(Tool.is_active == True).all()  # noqa: E712
