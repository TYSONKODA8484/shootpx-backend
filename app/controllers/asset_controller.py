import os

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.permissions import compute_permissions, get_membership
from app.core.storage import storage
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import new_id
from app.models.user import User


async def upload_asset(db: Session, team_id: str, current_user: User, file: UploadFile) -> Asset:
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
