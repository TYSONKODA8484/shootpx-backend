from typing import Any

from pydantic import BaseModel, field_validator

from app.models.generation_job import JobStatus


class GenerateRequest(BaseModel):
    team_id: str
    feature_type: str
    source_asset_id: str | None = None
    input_payload: dict[str, Any] = {}

    @field_validator("feature_type")
    @classmethod
    def feature_type_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("feature_type cannot be blank")
        return v


class GenerationJobOut(BaseModel):
    id: str
    team_id: str
    created_by: str
    feature_type: str
    status: JobStatus
    source_asset_id: str | None
    output_asset_id: str | None
    error: str | None

    class Config:
        from_attributes = True
