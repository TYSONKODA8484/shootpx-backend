from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import compute_permissions, get_membership
from app.core.queue import enqueue_product_import
from app.models.asset import Asset
from app.models.product_import import ProductImport, ProductImportStatus
from app.models.user import User
from app.schemas.product_import import ImportedImageRef, ProductImportOut, ProductImportRequest


async def start_product_import(
    db: Session, current_user: User, payload: ProductImportRequest
) -> ProductImport:
    membership = get_membership(db, payload.team_id, current_user.id)
    if not compute_permissions(membership.role).can_upload_assets:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to import assets on this team"
        )

    imp = ProductImport(
        team_id=payload.team_id,
        created_by=current_user.id,
        source_url=payload.url,
        status=ProductImportStatus.processing.value,
    )
    db.add(imp)
    db.commit()
    db.refresh(imp)

    # Same honest-failure pattern as run_generation: if enqueueing itself
    # fails (e.g. Redis unreachable), mark it failed now rather than
    # leaving it stuck at "processing" forever with nothing to pick it up.
    try:
        await enqueue_product_import(imp.id)
    except Exception as exc:
        imp.status = ProductImportStatus.failed.value
        imp.error = f"Failed to enqueue: {exc}"
        imp.completed_at = datetime.utcnow()
        db.commit()
        raise

    return imp


def get_product_import(db: Session, current_user: User, import_id: str) -> ProductImportOut:
    imp = db.get(ProductImport, import_id)
    if imp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product import not found")

    get_membership(db, imp.team_id, current_user.id)

    images = db.query(Asset).filter(Asset.product_import_id == imp.id).all()
    return _to_out(imp, images)


def _to_out(imp: ProductImport, images: list[Asset]) -> ProductImportOut:
    return ProductImportOut(
        id=imp.id,
        team_id=imp.team_id,
        source_url=imp.source_url,
        status=imp.status,
        product_name=imp.product_name,
        product_description=imp.product_description,
        brand_name=imp.brand_name,
        price=imp.price,
        theme_colors=imp.theme_colors,
        images=[ImportedImageRef(id=a.id, url=a.url, media_type=a.media_type) for a in images],
        error=imp.error,
    )
