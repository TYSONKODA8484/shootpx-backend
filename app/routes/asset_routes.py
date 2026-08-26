from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.controllers import asset_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.assets import AssetListOut, AssetOut, AssetUpdate, AssetVersionsOut
from app.schemas.exports import ExportRequest, ExportResponse

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


@router.patch("/assets/{asset_id}", response_model=AssetOut)
def update_asset(
    asset_id: str,
    payload: AssetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return asset_controller.update_asset(db, asset_id, current_user, is_saved_product=payload.is_saved_product)


@router.post("/assets/{asset_id}/export", response_model=ExportResponse)
def export_asset(
    asset_id: str,
    payload: ExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return asset_controller.export_asset(db, asset_id, current_user, payload.presets)


@router.get("/assets/{asset_id}/versions", response_model=AssetVersionsOut)
def get_asset_versions(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return asset_controller.get_asset_versions(db, asset_id, current_user)
