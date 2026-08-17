from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import compute_permissions, get_membership
from app.core.queue import enqueue_generation_job
from app.models.asset import Asset
from app.models.generation_job import GenerationJob, JobStatus
from app.models.user import User
from app.schemas.generation import GenerateRequest


async def run_generation(db: Session, current_user: User, payload: GenerateRequest) -> GenerationJob:
    membership = get_membership(db, payload.team_id, current_user.id)
    if not compute_permissions(membership.role).can_generate:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to generate on this team")

    source_asset = None
    if payload.source_asset_id:
        source_asset = db.get(Asset, payload.source_asset_id)
        if not source_asset or source_asset.team_id != payload.team_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="source_asset_id does not belong to this team"
            )

    job = GenerationJob(
        team_id=payload.team_id,
        created_by=current_user.id,
        feature_type=payload.feature_type,
        status=JobStatus.processing.value,
        source_asset_id=source_asset.id if source_asset else None,
        input_payload=payload.input_payload,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Real work happens in app/worker.py:run_generation_job, once that
    # team's lock is free and a global worker slot is available. If
    # enqueueing itself fails (e.g. Redis unreachable), mark the job
    # honestly failed rather than leaving it stuck at "processing" forever
    # with nothing ever going to pick it up.
    try:
        await enqueue_generation_job(job.id, payload.team_id)
    except Exception as exc:
        job.status = JobStatus.failed.value
        job.error = f"Failed to enqueue: {exc}"
        job.completed_at = datetime.utcnow()
        db.commit()
        raise

    return job
