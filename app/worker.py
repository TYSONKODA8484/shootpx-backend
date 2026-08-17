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
If the per-team lock is held, the job re-queues itself via arq's Retry
rather than blocking — so a job waiting on someone else's lock does not
tie up one of the global max_jobs slots while it waits.
"""

import asyncio
from datetime import datetime

from arq import Retry
from arq.connections import RedisSettings
from redis.asyncio import Redis

from app.core.ai_provider import ai_provider
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
# without releasing, the team isn't wedged forever, just until this expires
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

    acquired = await redis.set(lock_key, job_id, nx=True, ex=LOCK_TTL_SECONDS)
    if not acquired:
        raise Retry(defer=LOCK_RETRY_DELAY_SECONDS)

    try:
        await _process_job(job_id)
    finally:
        await redis.eval(_UNLOCK_IF_OURS, 1, lock_key, job_id)


async def _process_job(job_id: str) -> None:
    """Runs the actual generation. Note: ai_provider.generate(), storage.save(),
    and every DB call here are synchronous and block this coroutine's event
    loop for their duration — harmless while ai_provider is the instant mock,
    but once a real (slower, network-bound) provider replaces it, this will
    stall other concurrently-running jobs in the same worker process, making
    MAX_CONCURRENT_GENERATIONS less effective than it looks. Wrap the blocking
    calls in asyncio.to_thread(...) (or move to async equivalents) at that point.
    """
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return  # defensive: shouldn't happen, job row is created before enqueue

        source_asset = db.get(Asset, job.source_asset_id) if job.source_asset_id else None
        try:
            if settings.MOCK_GENERATION_DELAY_SECONDS:
                await asyncio.sleep(settings.MOCK_GENERATION_DELAY_SECONDS)

            result = ai_provider.generate(
                feature_type=job.feature_type,
                source_asset_url=source_asset.url if source_asset else None,
                input_payload=job.input_payload,
            )
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
        except asyncio.CancelledError:
            job.status = JobStatus.failed.value
            job.error = "Generation timed out"
            job.completed_at = datetime.utcnow()
            db.commit()
            raise  # let arq's own cancellation/retry machinery still see this
        except Exception as exc:
            job.status = JobStatus.failed.value
            job.error = str(exc)
            job.completed_at = datetime.utcnow()

        db.commit()
    finally:
        db.close()


class WorkerSettings:
    functions = [run_generation_job]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = settings.MAX_CONCURRENT_GENERATIONS
    job_timeout = 300  # generous; real AI calls later may take a while
    max_tries = 10_000  # lock-contention retries (arq.Retry, 0.5s apart)
    # aren't real failures, just polling for the per-team lock to free up —
    # they shouldn't count toward arq's normal retry-then-give-up budget.
    # Bounded in practice by LOCK_TTL_SECONDS (a lock can't be held forever)
    # and by how many jobs can realistically queue behind one team.
