from typing import Any

from pydantic import BaseModel


class TemplateOut(BaseModel):
    id: str
    name: str
    category: str
    feature_type: str
    credit_cost: int
    preview_asset_url: str | None
    input_payload_preset: dict[str, Any]

    class Config:
        from_attributes = True


class TemplateListOut(BaseModel):
    total: int
    templates: list[TemplateOut]
