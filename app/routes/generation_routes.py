from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.controllers import generation_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.generation import (
    BatchStatusOut,
    BulkGenerateRequest,
    BulkGenerateResponse,
    GenerateRequest,
    GenerationJobOut,
    GenerationJobSummary,
)

router = APIRouter(tags=["generation"])


@router.post("/generate", response_model=GenerationJobOut, status_code=status.HTTP_201_CREATED)
async def generate(
    payload: GenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await generation_controller.run_generation(db, current_user, payload)


@router.post("/generate/bulk", response_model=BulkGenerateResponse, status_code=status.HTTP_201_CREATED)
async def generate_bulk(
    payload: BulkGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await generation_controller.run_generation_bulk(db, current_user, payload)


@router.get("/jobs", response_model=list[GenerationJobSummary])
def list_jobs(
    ids: str = Query(..., description="Comma-separated job ids"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job_ids = [i.strip() for i in ids.split(",") if i.strip()]
    return generation_controller.get_job_summaries(db, current_user, job_ids)


@router.get("/batches/{batch_id}", response_model=BatchStatusOut)
def get_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return generation_controller.get_batch_status(db, current_user, batch_id)
