import os

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core import cache
from app.core.permissions import compute_permissions, get_membership
from app.core.storage import storage
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import new_id
from app.models.user import User
from app.schemas.assets import AssetListOut


async def create_asset_from_upload(db: Session, team_id: str, current_user: User, file: UploadFile) -> Asset:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_upload_assets:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to upload assets to this team")

    content_type = file.content_type or ""
    if content_type.startswith("image/"):
        media_type = MediaType.image
    elif content_type.startswith("video/"):
        media_type = MediaType.video
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {content_type or 'unknown'} (expected image/* or video/*)",
        )

    ext = os.path.splitext(file.filename or "")[1]
    key = f"{team_id}/{new_id()}{ext}"
    content = await file.read()
    storage.save(key, content)

    asset = Asset(
        team_id=team_id,
        created_by=current_user.id,
        kind=AssetKind.upload.value,
        media_type=media_type.value,
        storage_key=key,
        url=storage.url_for(key),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


async def upload_asset(db: Session, team_id: str, current_user: User, file: UploadFile) -> Asset:
    return await create_asset_from_upload(db, team_id, current_user, file)


def list_assets(
    db: Session,
    team_id: str,
    current_user: User,
    kind: str | None = None,
    media_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AssetListOut:
    get_membership(db, team_id, current_user.id)  # 404s if not a member — same
    # "don't confirm existence" pattern every other team-scoped read uses.

    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    query = db.query(Asset).filter(Asset.team_id == team_id)
    if kind:
        query = query.filter(Asset.kind == kind)
    if media_type:
        query = query.filter(Asset.media_type == media_type)

    total = query.count()
    assets = query.order_by(Asset.created_at.desc()).offset(offset).limit(limit).all()
    return AssetListOut(total=total, assets=assets)


def delete_asset(db: Session, asset_id: str, current_user: User) -> None:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    membership = get_membership(db, asset.team_id, current_user.id)
    if not compute_permissions(membership.role).can_upload_assets:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to delete assets on this team")

    storage.delete(asset.storage_key)
    cache.delete("media", asset.id)
    db.delete(asset)
    db.commit()
    # GenerationJob.output_asset_id rows pointing at this asset are left as
    # they are, on purpose — no cascade. A job stays queryable audit history
    # even after its output asset is gone; the frontend just handles a
    # 404'd image URL. See BACKEND-NEEDS.md's B1 section for the reasoning.


def update_asset(db: Session, asset_id: str, current_user: User, is_saved_product: bool) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    membership = get_membership(db, asset.team_id, current_user.id)
    if not compute_permissions(membership.role).can_upload_assets:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to edit assets on this team")

    asset.is_saved_product = is_saved_product
    db.commit()
    db.refresh(asset)
    return asset
