from pydantic import BaseModel, field_validator

from app.models.asset import MediaType
from app.models.product_import import ProductImportStatus


class ProductImportRequest(BaseModel):
    team_id: str
    url: str

    @field_validator("url")
    @classmethod
    def url_looks_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("url cannot be blank")
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url must start with http:// or https://")
        return v


class ImportedImageRef(BaseModel):
    id: str
    url: str
    media_type: MediaType


class ProductImportOut(BaseModel):
    id: str
    team_id: str
    source_url: str
    status: ProductImportStatus
    product_name: str | None
    product_description: str | None
    brand_name: str | None
    price: str | None
    theme_colors: list[str] | None
    images: list[ImportedImageRef]
    error: str | None
