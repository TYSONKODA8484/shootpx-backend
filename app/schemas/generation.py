from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.asset import MediaType
from app.models.generation_job import JobStatus


def _not_blank(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("feature_type cannot be blank")
    return v


class GenerateRequest(BaseModel):
    team_id: str
    feature_type: str
    source_asset_id: str | None = None
    input_payload: dict[str, Any] = {}

    @field_validator("feature_type")
    @classmethod
    def feature_type_not_blank(cls, v: str) -> str:
        return _not_blank(v)


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


class BulkGenerateRequest(BaseModel):
    team_id: str
    feature_type: str
    asset_ids: list[str] = Field(min_length=1, max_length=100)
    input_payload: dict[str, Any] = {}

    @field_validator("feature_type")
    @classmethod
    def feature_type_not_blank(cls, v: str) -> str:
        return _not_blank(v)


class BulkGenerateResponse(BaseModel):
    batch_id: str
    job_ids: list[str]


class AssetRef(BaseModel):
    url: str
    media_type: MediaType


class GenerationJobSummary(BaseModel):
    id: str
    feature_type: str
    status: JobStatus
    input: AssetRef | None
    output: AssetRef | None
    error: str | None


class BatchStatusOut(BaseModel):
    batch_id: str
    total: int
    done: int
    processing: int
    failed: int
    jobs: list[GenerationJobSummary]
