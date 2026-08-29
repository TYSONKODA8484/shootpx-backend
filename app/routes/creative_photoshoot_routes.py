from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import creative_photoshoot_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.creative_photoshoot import CreativePromptRequest, CreativePromptResponse

router = APIRouter(tags=["creative-photoshoot"])


@router.post("/teams/{team_id}/creative-photoshoot/prompt", response_model=CreativePromptResponse)
def build_prompt(
    team_id: str,
    payload: CreativePromptRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return creative_photoshoot_controller.build_prompt(db, team_id, current_user, payload)
