"""Brand Kit — marks (logo variants), palette, type, all scoped one-per-team.
Marks upload reuses asset_controller.create_asset_from_upload() so a mark
IS a real Asset (kind='upload'), not a separate file-storage path.
"""

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.controllers.asset_controller import create_asset_from_upload
from app.core.permissions import compute_permissions, get_membership
from app.models.brand_kit import BrandKit, BrandMark
from app.models.user import User
from app.schemas.brand_kit import BrandKitOut, BrandKitUpdate, BrandMarkOut


def _to_out(kit: BrandKit) -> BrandKitOut:
    return BrandKitOut(
        id=kit.id, team_id=kit.team_id, palette=kit.palette or [],
        heading_font=kit.heading_font, body_font=kit.body_font,
        marks=[
            BrandMarkOut(id=m.id, asset_id=m.asset_id, variant=m.variant, url=m.asset.url)
            for m in kit.marks
        ],
    )


def get_or_create_brand_kit(db: Session, team_id: str, current_user: User) -> BrandKitOut:
    get_membership(db, team_id, current_user.id)
    kit = db.query(BrandKit).filter(BrandKit.team_id == team_id).first()
    if kit is None:
        kit = BrandKit(team_id=team_id, palette=[])
        db.add(kit)
        db.commit()
        db.refresh(kit)
    return _to_out(kit)


def update_brand_kit(db: Session, team_id: str, current_user: User, payload: BrandKitUpdate) -> BrandKitOut:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_upload_assets:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to edit this team's brand kit")

    kit = db.query(BrandKit).filter(BrandKit.team_id == team_id).first()
    if kit is None:
        kit = BrandKit(team_id=team_id)
        db.add(kit)

    kit.palette = payload.palette
    kit.heading_font = payload.heading_font
    kit.body_font = payload.body_font
    db.commit()
    db.refresh(kit)
    return _to_out(kit)


async def add_mark(db: Session, team_id: str, current_user: User, file: UploadFile, variant: str) -> BrandMarkOut:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_upload_assets:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to edit this team's brand kit")

    kit = db.query(BrandKit).filter(BrandKit.team_id == team_id).first()
    if kit is None:
        kit = BrandKit(team_id=team_id, palette=[])
        db.add(kit)
        db.commit()
        db.refresh(kit)

    asset = await create_asset_from_upload(db, team_id, current_user, file)
    mark = BrandMark(brand_kit_id=kit.id, asset_id=asset.id, variant=variant)
    db.add(mark)
    db.commit()
    db.refresh(mark)
    return BrandMarkOut(id=mark.id, asset_id=asset.id, variant=mark.variant, url=asset.url)


def delete_mark(db: Session, mark_id: str, current_user: User) -> None:
    mark = db.get(BrandMark, mark_id)
    if mark is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand mark not found")

    kit = db.get(BrandKit, mark.brand_kit_id)
    membership = get_membership(db, kit.team_id, current_user.id)
    if not compute_permissions(membership.role).can_upload_assets:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to edit this team's brand kit")

    db.delete(mark)  # only the link row — the underlying Asset is untouched
    db.commit()
