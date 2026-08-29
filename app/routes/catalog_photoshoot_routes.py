from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import catalog_photoshoot_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.catalog_photoshoot import CatalogShotsRequest, CatalogShotsResponse

router = APIRouter(tags=["catalog-photoshoot"])


@router.post("/teams/{team_id}/catalog-photoshoot/shots", response_model=CatalogShotsResponse)
def build_shots(
    team_id: str,
    payload: CatalogShotsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return catalog_photoshoot_controller.build_shots(db, team_id, current_user, payload)
