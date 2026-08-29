from typing import Literal

from pydantic import BaseModel


class ModelImageResolveRequest(BaseModel):
    mode: Literal["generate", "upload", "default"]
    # generate:
    gender: str = ""
    age_bracket: str = ""
    skin_tone: str = ""
    body_type: str = ""
    additional_notes: str = ""
    # upload: an Asset the caller already created via POST /teams/{id}/assets
    asset_id: str | None = None
    # default:
    preset_id: str | None = None


class ModelImageResolveResponse(BaseModel):
    asset_id: str | None
    url: str
    clean: bool
    reason: str | None = None
    description: str | None = None


class PromptsRequest(BaseModel):
    model_image_url: str
    garment_asset_ids: list[str]
    reference_asset_ids: list[str] = []
    garment_type: str = "bra"
    num_poses: int = 4
    user_prompt: str | None = None
    resolution_mode: str = "standard"
    aspect_ratio: str = "3:4"
    custom_width: int | None = None
    custom_height: int | None = None


class PromptsResponse(BaseModel):
    prompts: list[str]
    image_urls: list[str]
    labels: list[str]
    image_size: dict | str
