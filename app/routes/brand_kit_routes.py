from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.controllers import brand_kit_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.brand_kit import BrandKitOut, BrandKitUpdate, BrandMarkOut

router = APIRouter(tags=["brand-kit"])


@router.get("/teams/{team_id}/brand-kit", response_model=BrandKitOut)
def get_brand_kit(team_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return brand_kit_controller.get_or_create_brand_kit(db, team_id, current_user)


@router.put("/teams/{team_id}/brand-kit", response_model=BrandKitOut)
def update_brand_kit(
    team_id: str,
    payload: BrandKitUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return brand_kit_controller.update_brand_kit(db, team_id, current_user, payload)


@router.post("/teams/{team_id}/brand-kit/marks", response_model=BrandMarkOut, status_code=status.HTTP_201_CREATED)
async def add_brand_mark(
    team_id: str,
    file: UploadFile = File(...),
    variant: str = Form(default="default"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await brand_kit_controller.add_mark(db, team_id, current_user, file, variant)


@router.delete("/brand-kit/marks/{mark_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_brand_mark(mark_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    brand_kit_controller.delete_mark(db, mark_id, current_user)
