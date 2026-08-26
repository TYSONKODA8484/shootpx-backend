import os

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core import cache
from app.core.credits import apply_credit_delta, get_balance
from app.core.image_ops import EXPORT_PRESETS, export_variant
from app.core.permissions import compute_permissions, get_membership
from app.core.storage import storage
from app.models.asset import Asset, AssetKind, MediaType
from app.models.credit import CreditReason
from app.models.team import new_id
from app.models.user import User
from app.schemas.assets import AssetListOut
from app.schemas.exports import ExportResponse, ExportResultItem


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


def export_asset(db: Session, asset_id: str, current_user: User, presets: list[str]) -> ExportResponse:
    source = db.get(Asset, asset_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    membership = get_membership(db, source.team_id, current_user.id)
    if not compute_permissions(membership.role).can_upload_assets:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to export assets on this team")

    unknown = [p for p in presets if p not in EXPORT_PRESETS]
    if unknown:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown export preset(s): {', '.join(unknown)}")

    cost = len(presets)  # 1 credit per preset — no "held credits" concept
    # needed here (unlike generation_controller's), since this runs
    # synchronously, not queued: nothing can race it mid-flight.
    balance = get_balance(db, source.team_id)
    if balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits: need {cost}, have {balance}",
        )

    content = storage.read(source.storage_key)
    exports: list[ExportResultItem] = []
    for preset in presets:
        result_bytes, ext = export_variant(content, preset)
        key = f"{source.team_id}/exports/{new_id()}.{ext}"
        storage.save(key, result_bytes)
        exported_asset = Asset(
            team_id=source.team_id,
            created_by=current_user.id,
            kind=AssetKind.exported.value,
            media_type=MediaType.image.value,
            storage_key=key,
            url=storage.url_for(key),
            source_asset_id=source.id,
        )
        db.add(exported_asset)
        db.commit()
        db.refresh(exported_asset)
        exports.append(ExportResultItem(preset=preset, asset_id=exported_asset.id, url=exported_asset.url))

    apply_credit_delta(db, source.team_id, amount=-cost, reason=CreditReason.export_spend.value, reference_id=source.id)
    db.commit()  # apply_credit_delta doesn't commit itself — every other
    # caller (app/worker.py) commits right after it; without this, the
    # balance update + ledger row stay pending and vanish when the
    # request's session closes uncommitted.
    return ExportResponse(exports=exports)
