from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import recolor_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.recolor import RecolorPromptRequest, RecolorPromptResponse

router = APIRouter(tags=["recolor"])


@router.post("/teams/{team_id}/recolor/prompt", response_model=RecolorPromptResponse)
def build_prompt(
    team_id: str,
    payload: RecolorPromptRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return recolor_controller.build_prompt(db, team_id, current_user, payload)
