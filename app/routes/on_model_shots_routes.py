from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import on_model_shots_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.on_model_shots import (
    ModelImageResolveRequest,
    ModelImageResolveResponse,
    PromptsRequest,
    PromptsResponse,
)

router = APIRouter(tags=["on-model-shots"])


@router.post("/teams/{team_id}/on-model-shots/model-image", response_model=ModelImageResolveResponse)
def resolve_model_image(
    team_id: str,
    payload: ModelImageResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return on_model_shots_controller.resolve_model_image(db, team_id, current_user, payload)


@router.post("/teams/{team_id}/on-model-shots/prompts", response_model=PromptsResponse)
def build_prompts(
    team_id: str,
    payload: PromptsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return on_model_shots_controller.build_prompts(db, team_id, current_user, payload)
