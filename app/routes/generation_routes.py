from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.controllers import generation_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.generation import GenerateRequest, GenerationJobOut

router = APIRouter(tags=["generation"])


@router.post("/generate", response_model=GenerationJobOut, status_code=status.HTTP_201_CREATED)
def generate(
    payload: GenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return generation_controller.run_generation(db, current_user, payload)
