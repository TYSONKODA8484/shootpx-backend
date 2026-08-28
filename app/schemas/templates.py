from typing import Any

from pydantic import BaseModel, ConfigDict


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    category: str
    feature_type: str
    credit_cost: int
    preview_asset_url: str | None
    input_payload_preset: dict[str, Any]

class TemplateListOut(BaseModel):
    total: int
    templates: list[TemplateOut]
