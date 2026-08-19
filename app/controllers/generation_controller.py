from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.asset_lookup import get_assets_cached
from app.core.credits import get_balance
from app.core.permissions import compute_permissions, get_membership
from app.core.pricing import resolve_credit_cost
from app.core.queue import enqueue_generation_job
from app.models.asset import Asset
from app.models.generation_job import GenerationJob, JobStatus
from app.models.team import TeamMembership, new_id
from app.models.tool import Tool
from app.models.user import User
from app.schemas.generation import (
    AssetRef,
    BatchStatusOut,
    BulkGenerateRequest,
    BulkGenerateResponse,
    GenerateRequest,
    GenerationJobSummary,
)


def _check_tool_active(db: Session, feature_type: str) -> None:
    """schemas/generation.py already rejects an unknown feature_type (422,
    checked against the CODE registry). This is a separate, DB-side check —
    is a genuinely real tool currently switched off (Tool.is_active) — so a
    tool can be disabled without a redeploy. Fails OPEN if the row is
    somehow missing (defensive — code-registry existence is still the hard
    requirement enforced at the schema layer), fails CLOSED only on an
    explicit is_active=False."""
    tool_row = db.get(Tool, feature_type)
    if tool_row is not None and not tool_row.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Tool {feature_type!r} is currently disabled")


def _held_credits(db: Session, team_id: str) -> int:
    """Sum of credit_cost across this team's jobs that are still
    'processing' — credits already committed to in-flight work but not yet
    deducted (deduction only happens on success, app/worker.py). Without
    this, rapid-fire /generate calls could all pass the balance check
    before any of the first ones actually complete and deduct — a real
    race, not hypothetical: caught by this project's own verification
    script submitting 5 jobs back to back with a 3s mock delay. The
    per-team generation LOCK doesn't prevent this either — it only
    serializes the worker's processing, not how many job rows the API will
    accept before the first one finishes."""
    held = (
        db.query(GenerationJob)
        .filter(GenerationJob.team_id == team_id, GenerationJob.status == JobStatus.processing.value)
        .with_entities(GenerationJob.credit_cost)
        .all()
    )
    return sum(cost for (cost,) in held if cost)


def _resolve_and_check_credits(db: Session, team_id: str, feature_type: str, input_payload: dict, job_count: int = 1) -> int:
    """Resolves the per-job credit cost (core/pricing.py) and checks the
    team can afford job_count of them, accounting for what's already held
    by in-flight jobs — 402 if short. Returns the per-job cost; the caller
    stores it on GenerationJob.credit_cost at submission time, never
    recomputed later (see BOOK.md Chapter 17 for why)."""
    per_job_cost = resolve_credit_cost(db, feature_type, input_payload)
    total_cost = per_job_cost * job_count
    balance = get_balance(db, team_id) - _held_credits(db, team_id)
    if balance < total_cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits: need {total_cost}, have {balance}",
        )
    return per_job_cost


async def run_generation(db: Session, current_user: User, payload: GenerateRequest) -> GenerationJob:
    membership = get_membership(db, payload.team_id, current_user.id)
    if not compute_permissions(membership.role).can_generate:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to generate on this team")
    _check_tool_active(db, payload.feature_type)
    per_job_cost = _resolve_and_check_credits(db, payload.team_id, payload.feature_type, payload.input_payload)

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
        credit_cost=per_job_cost,
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


async def run_generation_bulk(
    db: Session, current_user: User, payload: BulkGenerateRequest
) -> BulkGenerateResponse:
    membership = get_membership(db, payload.team_id, current_user.id)
    if not compute_permissions(membership.role).can_generate:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to generate on this team")
    _check_tool_active(db, payload.feature_type)

    found = (
        db.query(Asset)
        .filter(Asset.id.in_(payload.asset_ids), Asset.team_id == payload.team_id)
        .all()
    )
    found_ids = {a.id for a in found}
    missing = [aid for aid in payload.asset_ids if aid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"asset_ids not found in this team: {', '.join(missing)}",
        )

    # Checked for the WHOLE batch upfront, same all-or-nothing philosophy
    # as the asset-existence check above — every job in a bulk call shares
    # one feature_type + input_payload, so they all cost the same per-job
    # amount; short on credits for the batch fails the whole request rather
    # than silently generating a partial batch.
    per_job_cost = _resolve_and_check_credits(
        db, payload.team_id, payload.feature_type, payload.input_payload, job_count=len(payload.asset_ids)
    )

    batch_id = new_id()
    jobs = [
        GenerationJob(
            team_id=payload.team_id,
            created_by=current_user.id,
            feature_type=payload.feature_type,
            status=JobStatus.processing.value,
            source_asset_id=asset_id,
            batch_id=batch_id,
            input_payload=payload.input_payload,
            credit_cost=per_job_cost,
        )
        for asset_id in payload.asset_ids
    ]
    db.add_all(jobs)
    db.flush()  # populates job.id (the model's Python-side new_id default) without
    # expiring anything yet — captured below, before db.commit() expires all
    # attributes (SessionLocal never sets expire_on_commit=False, so re-reading
    # .id off these objects after commit would trigger one implicit SELECT per job)
    job_ids = [job.id for job in jobs]
    db.commit()

    # Same enqueue as single /generate — the per-team lock is what makes
    # these run one after another, not a separate batch mechanism. Each
    # job is enqueued independently: if enqueueing one fails (e.g. Redis
    # blips mid-loop), that job is marked failed honestly rather than left
    # stuck at "processing" forever — same fix already applied to single
    # /generate in Task 4 — but the rest of the batch still gets its shot.
    for job, job_id in zip(jobs, job_ids):
        try:
            await enqueue_generation_job(job_id, payload.team_id)
        except Exception as exc:
            job.status = JobStatus.failed.value
            job.error = f"Failed to enqueue: {exc}"
            job.completed_at = datetime.utcnow()
            db.commit()

    return BulkGenerateResponse(batch_id=batch_id, job_ids=job_ids)


def _to_summaries(db: Session, jobs: list[GenerationJob]) -> list[GenerationJobSummary]:
    asset_ids = {j.source_asset_id for j in jobs if j.source_asset_id}
    asset_ids |= {j.output_asset_id for j in jobs if j.output_asset_id}
    # Cached (core/asset_lookup.py, "media" namespace) — GET /jobs and GET
    # /batches/{id} both land here and get polled repeatedly while a job
    # is running, re-resolving the same source/output asset ids every time.
    assets = get_assets_cached(db, asset_ids)

    def ref(asset_id: str | None) -> AssetRef | None:
        asset = assets.get(asset_id) if asset_id else None
        return AssetRef(url=asset.url, media_type=asset.media_type) if asset else None

    return [
        GenerationJobSummary(
            id=j.id,
            feature_type=j.feature_type,
            status=j.status,
            input=ref(j.source_asset_id),
            output=ref(j.output_asset_id),
            error=j.error,
        )
        for j in jobs
    ]


def get_job_summaries(db: Session, current_user: User, job_ids: list[str]) -> list[GenerationJobSummary]:
    if not job_ids:
        return []
    jobs_by_id = {
        j.id: j for j in db.query(GenerationJob).filter(GenerationJob.id.in_(job_ids)).all()
    }
    team_ids = {j.team_id for j in jobs_by_id.values()}
    accessible_team_ids = (
        {
            m.team_id
            for m in db.query(TeamMembership)
            .filter(TeamMembership.team_id.in_(team_ids), TeamMembership.user_id == current_user.id)
            .all()
        }
        if team_ids
        else set()
    )
    accessible = [
        jobs_by_id[jid]
        for jid in job_ids
        if jid in jobs_by_id and jobs_by_id[jid].team_id in accessible_team_ids
    ]
    return _to_summaries(db, accessible)


def get_batch_status(db: Session, current_user: User, batch_id: str) -> BatchStatusOut:
    jobs = db.query(GenerationJob).filter(GenerationJob.batch_id == batch_id).all()
    if not jobs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

    # Every job in a batch shares one team_id (bulk always scopes to a
    # single team) — same membership check used everywhere else, raises
    # 404 rather than 403 for non-members, same as get_membership always has.
    get_membership(db, jobs[0].team_id, current_user.id)

    done = sum(1 for j in jobs if j.status == JobStatus.done.value)
    failed = sum(1 for j in jobs if j.status == JobStatus.failed.value)
    return BatchStatusOut(
        batch_id=batch_id,
        total=len(jobs),
        done=done,
        processing=len(jobs) - done - failed,
        failed=failed,
        jobs=_to_summaries(db, jobs),
    )
