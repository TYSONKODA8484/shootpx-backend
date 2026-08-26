from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.controllers import asset_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.assets import AssetListOut, AssetOut

router = APIRouter(tags=["assets"])


@router.post("/teams/{team_id}/assets", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    team_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await asset_controller.upload_asset(db, team_id, current_user, file)


@router.get("/teams/{team_id}/assets", response_model=AssetListOut)
def list_assets(
    team_id: str,
    kind: str | None = Query(default=None),
    media_type: str | None = Query(default=None),
    limit: int = Query(default=50, le=200, gt=0),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return asset_controller.list_assets(
        db, team_id, current_user, kind=kind, media_type=media_type, limit=limit, offset=offset
    )


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset_controller.delete_asset(db, asset_id, current_user)
