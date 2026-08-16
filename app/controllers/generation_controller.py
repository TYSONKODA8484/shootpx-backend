from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.ai_provider import ai_provider
from app.core.permissions import compute_permissions, get_membership
from app.core.storage import storage
from app.models.asset import Asset, AssetKind
from app.models.generation_job import GenerationJob, JobStatus
from app.models.team import new_id
from app.models.user import User
from app.schemas.generation import GenerateRequest


def run_generation(db: Session, current_user: User, payload: GenerateRequest) -> GenerationJob:
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

    # No queue/worker yet — v1 is deliberately synchronous. Whatever runs the
    # 23 tools' real logic later can dispatch on feature_type right here.
    try:
        result = ai_provider.generate(
            feature_type=payload.feature_type,
            source_asset_url=source_asset.url if source_asset else None,
            input_payload=payload.input_payload,
        )
        key = f"{payload.team_id}/generated/{new_id()}.{result.extension}"
        storage.save(key, result.content)

        output_asset = Asset(
            team_id=payload.team_id,
            created_by=current_user.id,  # attributed to whoever triggered the job, not the AI
            kind=AssetKind.generated.value,
            media_type=result.media_type,
            storage_key=key,
            url=storage.url_for(key),
        )
        db.add(output_asset)
        db.flush()  # get output_asset.id before attaching it to the job

        job.output_asset_id = output_asset.id
        job.status = JobStatus.done.value
        job.completed_at = datetime.utcnow()
    except Exception as exc:
        job.status = JobStatus.failed.value
        job.error = str(exc)
        job.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(job)
    return job
