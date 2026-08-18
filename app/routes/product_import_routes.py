from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.controllers import product_import_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.product_import import ProductImportOut, ProductImportRequest

router = APIRouter(tags=["product-imports"])


@router.post("/product-imports", response_model=ProductImportOut, status_code=status.HTTP_201_CREATED)
async def create_product_import(
    payload: ProductImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    imp = await product_import_controller.start_product_import(db, current_user, payload)
    return product_import_controller.get_product_import(db, current_user, imp.id)


@router.get("/product-imports/{import_id}", response_model=ProductImportOut)
def get_product_import(
    import_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return product_import_controller.get_product_import(db, current_user, import_id)
