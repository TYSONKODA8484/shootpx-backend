"""arq worker entrypoint — runs as its own process, separate from the API
(locally: `uvicorn app.main:app --reload` in one terminal, `arq
app.worker.WorkerSettings` in another). Its one job, run_generation_job,
is what /generate and /generate/bulk both enqueue instead of calling the
AI provider inline.

Two independent limits apply to every job:
- a per-team Redis lock (SET NX EX below) — only one job for a given team
  runs at a time, whether it came from /generate or /generate/bulk. This
  is also the entire mechanism behind bulk's "one after another": there's
  no separate batch-processing code path, just this same lock.
- arq's own `max_jobs` (WorkerSettings, bottom of this file) — caps total
  concurrently *running* jobs across every team combined.
If the per-team lock is held by someone else, the job re-queues itself via
arq's Retry rather than blocking — so a job waiting on someone else's lock
does not tie up one of the global max_jobs slots while it waits.

Submitting to and polling the AI provider (app/core/ai_provider.py) works
the same way: a real aggregator (fal.ai, Segmind, ...) takes seconds to
minutes to actually generate something, so run_generation_job never blocks
waiting for that. One invocation does exactly one fast thing — submit the
job, or check its status once — and if the provider isn't done yet, the
job requeues itself via Retry(defer=GENERATION_POLL_INTERVAL_SECONDS) and
gives up its worker slot in the meantime, same as the lock-wait case. This
means one job's total lifetime (submit -> N polls -> done) can span many
separate arq invocations, possibly on different worker processes if you're
running more than one — nothing about a job's progress is allowed to live
in this process's memory; it all round-trips through the GenerationJob row
(status, external_job_id, provider) and the Redis lock (which is refreshed,
not re-acquired, across those invocations — see run_generation_job below).
"""

from datetime import datetime

from arq import Retry
from arq.connections import RedisSettings
from redis.asyncio import Redis
from sqlalchemy.orm import Session

from app.core.ai_provider import GenerationFailed, GenerationHandle, GenerationPending, ai_provider
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.storage import storage
from app.models.asset import Asset, AssetKind
from app.models.generation_job import GenerationJob, JobStatus
from app.models.team import new_id
from app.models import invite as invite_models  # noqa: F401  (registers TeamInvite on Base —
# Team.invites references it by string; SQLAlchemy needs it imported in
# this process before mapper configuration runs, same as app/main.py)
from app.models import user as user_models  # noqa: F401  (registers User on Base —
# TeamMembership.user references it by string, same reason as above)

LOCK_TTL_SECONDS = 600  # generous ceiling: if a worker crashes mid-job
# without releasing, the team isn't wedged forever, just until this expires.
# Refreshed (not just set once) on every invocation that still holds it —
# see run_generation_job — so this is really "600s since the job was last
# touched", not "600s total", which matters now that one job can span many
# invocations while its provider job runs.
LOCK_RETRY_DELAY_SECONDS = 0.5

# Only delete the lock if it's still the value we set — otherwise a job
# that overran LOCK_TTL_SECONDS could delete a *different* job's lock that
# acquired it after ours expired. Standard safe-unlock pattern.
_UNLOCK_IF_OURS = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""


def _team_lock_key(team_id: str) -> str:
    return f"lock:team:{team_id}"


async def run_generation_job(ctx: dict, job_id: str, team_id: str) -> None:
    redis: Redis = ctx["redis"]
    lock_key = _team_lock_key(team_id)

    # Do we already hold this team's lock from an earlier invocation of this
    # same job (i.e. this is a poll retry, not the first try)? If so, just
    # refresh its TTL — SET NX would no-op here since the key still exists,
    # which would wrongly look like "someone else has it" below. redis-py
    # returns bytes here (arq's pool isn't set up with decode_responses),
    # so decode before comparing against the plain str job_id.
    current_holder = await redis.get(lock_key)
    if current_holder is not None and current_holder.decode() == job_id:
        await redis.expire(lock_key, LOCK_TTL_SECONDS)
    else:
        acquired = await redis.set(lock_key, job_id, nx=True, ex=LOCK_TTL_SECONDS)
        if not acquired:
            raise Retry(defer=LOCK_RETRY_DELAY_SECONDS)

    still_pending = await _process_job(job_id)
    if still_pending:
        # Don't unlock — we're still working this job (submitted, waiting
        # on the provider), the next retry will pick up right where this
        # one left off via external_job_id on the row.
        raise Retry(defer=settings.GENERATION_POLL_INTERVAL_SECONDS)

    await redis.eval(_UNLOCK_IF_OURS, 1, lock_key, job_id)


async def _process_job(job_id: str) -> bool:
    """Advances a job by exactly one step — submit if it hasn't been yet,
    otherwise one poll — and returns whether the caller should retry later
    (True: still running with the provider) or is done (False: the row is
    now in a terminal state, done or failed)."""
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return False  # defensive: shouldn't happen, job row is created before enqueue

        if job.external_job_id is None:
            return _submit(db, job)

        if (datetime.utcnow() - job.created_at).total_seconds() > settings.GENERATION_TIMEOUT_SECONDS:
            job.status = JobStatus.failed.value
            job.error = "Generation timed out"
            job.completed_at = datetime.utcnow()
            db.commit()
            return False

        return _poll(db, job)
    finally:
        db.close()


def _submit(db: Session, job: GenerationJob) -> bool:
    source_asset = db.get(Asset, job.source_asset_id) if job.source_asset_id else None
    try:
        handle = ai_provider.submit(
            feature_type=job.feature_type,
            source_asset_url=source_asset.url if source_asset else None,
            input_payload=job.input_payload,
        )
    except Exception as exc:
        job.status = JobStatus.failed.value
        job.error = str(exc)
        job.completed_at = datetime.utcnow()
        db.commit()
        return False

    job.external_job_id = handle.external_job_id
    job.provider = handle.provider
    db.commit()
    return True  # submitted; first poll happens on the next invocation


def _poll(db: Session, job: GenerationJob) -> bool:
    handle = GenerationHandle(external_job_id=job.external_job_id, provider=job.provider)
    try:
        result = ai_provider.poll_result(handle)
    except GenerationPending:
        return True
    except GenerationFailed as exc:
        job.status = JobStatus.failed.value
        job.error = str(exc)
        job.completed_at = datetime.utcnow()
        db.commit()
        return False
    except Exception as exc:
        # Our own error (network blip, provider unreachable, etc.), not the
        # provider reporting failure. Same outcome either way for now — the
        # job is marked failed rather than retried indefinitely; a
        # transient-vs-permanent distinction (retry network errors a few
        # times before giving up) can be added once a real provider's
        # actual failure modes are known.
        job.status = JobStatus.failed.value
        job.error = str(exc)
        job.completed_at = datetime.utcnow()
        db.commit()
        return False

    key = f"{job.team_id}/generated/{new_id()}.{result.extension}"
    storage.save(key, result.content)

    output_asset = Asset(
        team_id=job.team_id,
        created_by=job.created_by,
        kind=AssetKind.generated.value,
        media_type=result.media_type,
        storage_key=key,
        url=storage.url_for(key),
    )
    db.add(output_asset)
    db.flush()

    job.output_asset_id = output_asset.id
    job.status = JobStatus.done.value
    job.completed_at = datetime.utcnow()
    db.commit()
    return False


class WorkerSettings:
    functions = [run_generation_job]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = settings.MAX_CONCURRENT_GENERATIONS
    job_timeout = 300  # per invocation (one lock-wait check, one submit, or
    # one poll) — generous for a single HTTP call. Not the job's total
    # lifetime; that's GENERATION_TIMEOUT_SECONDS, checked in _process_job.
    max_tries = 10_000  # lock-contention retries and provider poll retries
    # both go through arq.Retry and both count against this budget — neither
    # is a real failure, just waiting (for the lock to free up, or for the
    # provider to finish). Bounded in practice by LOCK_TTL_SECONDS and
    # GENERATION_TIMEOUT_SECONDS respectively, not by this number.
