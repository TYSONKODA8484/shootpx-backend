"""arq connection pool used by the API process to enqueue generation jobs
and product imports. One pool per process, lazily created on first use and
reused after — same lazy-singleton pattern as the AI provider/storage
modules. The worker process (app/worker.py) never imports this file; it
gets its own connection via arq's WorkerSettings.
"""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings

_pool: ArqRedis | None = None


async def get_queue_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    return _pool


async def enqueue_generation_job(job_id: str, team_id: str, created_by: str) -> None:
    """Fire-and-forget: hands the job to arq and returns. The actual AI
    call happens later, in app/worker.py's run_generation_job, once that
    USER's lock is free (per-user, not per-team — different members of the
    same team can generate concurrently, see
    docs/superpowers/specs/2026-08-29-on-model-shots-real-provider-design.md's
    addendum) and a global worker slot is available."""
    pool = await get_queue_pool()
    await pool.enqueue_job("run_generation_job", job_id, team_id, created_by)


async def enqueue_product_import(import_id: str) -> None:
    """Same fire-and-forget shape as enqueue_generation_job. The actual
    scrape happens later, in app/worker.py's run_product_import, once a
    global worker slot is available — no per-team lock for imports."""
    pool = await get_queue_pool()
    await pool.enqueue_job("run_product_import", import_id)
