"""arq worker entrypoint — runs as its own process, separate from the API
(locally: `uvicorn app.main:app --reload` in one terminal, `arq
app.worker.WorkerSettings` in another). Two jobs live here: run_generation_job
(what /generate and /generate/bulk enqueue instead of calling the AI
provider inline) and run_product_import (what POST /product-imports
enqueues instead of calling the product-scrapper service inline) — same
submit/poll-via-Retry shape, different external system on the other end.

Two independent limits apply to every run_generation_job:
- a per-team Redis lock (SET NX EX below) — only one generation job for a
  given team runs at a time, whether it came from /generate or
  /generate/bulk. This is also the entire mechanism behind bulk's "one
  after another": there's no separate batch-processing code path, just
  this same lock.
- arq's own `max_jobs` (WorkerSettings, bottom of this file) — caps total
  concurrently *running* jobs across every team combined, generation and
  imports alike (they share one worker process's job pool for now — a
  dedicated cap/process split for imports is a reasonable thing to add
  once real traffic shows it's needed, not before).
If the per-team lock is held by someone else, the job re-queues itself via
arq's Retry rather than blocking — so a job waiting on someone else's lock
does not tie up one of the global max_jobs slots while it waits.
run_product_import has no per-team lock — nothing about scraping needs
one team's imports serialized against each other or against generation.

Which AIProvider instance actually runs a job is looked up per job from
app/tools/ (one file per tool, each registering itself into a shared
registry — see app/tools/registry.py), keyed by feature_type, not a single
hardcoded provider. Different tools can point at different providers (or
share one) without this file changing.

Submitting to and polling the AI provider (app/core/ai_provider.py) works
the same way regardless of which provider a tool resolves to: a real
aggregator (fal.ai, Segmind, ...) takes seconds to minutes to actually
generate something, so run_generation_job never blocks waiting for that.
One invocation does exactly one fast thing — submit the job, or check its
status once — and if the provider isn't done yet, the
job requeues itself via Retry(defer=GENERATION_POLL_INTERVAL_SECONDS) and
gives up its worker slot in the meantime, same as the lock-wait case. This
means one job's total lifetime (submit -> N polls -> done) can span many
separate arq invocations, possibly on different worker processes if you're
running more than one — nothing about a job's progress is allowed to live
in this process's memory; it all round-trips through the GenerationJob row
(status, external_job_id, provider) and the Redis lock (which is refreshed,
not re-acquired, across those invocations — see run_generation_job below).

run_product_import follows the identical submit/poll/Retry shape against a
different external system (core/product_scraper_client.py, talking to the
product-scrapper service — a separate repo/process, not this one), with
progress round-tripping through the ProductImport row instead
(status, external_job_id) — no lock to refresh, hence the simpler function.
Once the scrape itself is done, downloading each of its (possibly several)
result images and saving them as real Assets happens synchronously inline
here too — same "harmless for now, wrap in asyncio.to_thread once it
actually stalls concurrently-running jobs" tradeoff as storage.save() and
every DB call in this file already accept.
"""

from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from arq import Retry
from arq.connections import RedisSettings
from redis.asyncio import Redis
from sqlalchemy.orm import Session

from app.core import product_scraper_client
from app.core.ai_provider import GenerationFailed, GenerationHandle, GenerationPending
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.product_scraper_client import ScrapeHandle, ScrapePending
from app.core.storage import storage
from app.tools import get_tool
from app.models.asset import Asset, AssetKind, MediaType
from app.models.generation_job import GenerationJob, JobStatus
from app.models.product_import import ProductImport, ProductImportStatus
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
    tool = get_tool(job.feature_type)
    if tool is None:
        # Defense in depth: the API layer (schemas/generation.py) already
        # rejects unknown feature_type before a job is created, but the
        # registry is checked again here in case a job somehow reaches the
        # worker for a feature_type that's since been removed from it.
        job.status = JobStatus.failed.value
        job.error = f"Unknown feature_type: {job.feature_type!r}"
        job.completed_at = datetime.utcnow()
        db.commit()
        return False

    source_asset = db.get(Asset, job.source_asset_id) if job.source_asset_id else None
    try:
        handle = tool.provider.submit(
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
    tool = get_tool(job.feature_type)
    if tool is None:
        job.status = JobStatus.failed.value
        job.error = f"Unknown feature_type: {job.feature_type!r}"
        job.completed_at = datetime.utcnow()
        db.commit()
        return False

    handle = GenerationHandle(external_job_id=job.external_job_id, provider=job.provider)
    try:
        result = tool.provider.poll_result(handle)
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


MAX_IMPORTED_IMAGES = 20  # defensive cap — a pathological product page
# with hundreds of gallery images shouldn't turn one import into hundreds
# of downloads; not configurable via settings, this is a sanity ceiling,
# not a tuned value.

_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _guess_extension(image_url: str, content_type: str) -> str:
    suffix = Path(urlparse(image_url).path).suffix.lstrip(".").lower()
    if suffix in ("jpg", "jpeg", "png", "webp", "gif"):
        return "jpg" if suffix == "jpeg" else suffix
    return _EXTENSION_BY_CONTENT_TYPE.get(content_type.split(";")[0].strip().lower(), "jpg")


async def run_product_import(ctx: dict, import_id: str) -> None:
    still_pending = await _process_import(import_id)
    if still_pending:
        raise Retry(defer=settings.PRODUCT_IMPORT_POLL_INTERVAL_SECONDS)


async def _process_import(import_id: str) -> bool:
    """Same shape as _process_job: advances a ProductImport by exactly one
    step (submit if not yet submitted, otherwise one poll) and returns
    whether the caller should retry later."""
    db = SessionLocal()
    try:
        imp = db.get(ProductImport, import_id)
        if imp is None:
            return False  # defensive: shouldn't happen, row is created before enqueue

        if imp.external_job_id is None:
            return _submit_import(db, imp)

        if (datetime.utcnow() - imp.created_at).total_seconds() > settings.PRODUCT_IMPORT_TIMEOUT_SECONDS:
            imp.status = ProductImportStatus.failed.value
            imp.error = "Product import timed out"
            imp.completed_at = datetime.utcnow()
            db.commit()
            return False

        return _poll_import(db, imp)
    finally:
        db.close()


def _submit_import(db: Session, imp: ProductImport) -> bool:
    try:
        handle = product_scraper_client.submit(imp.source_url)
    except Exception as exc:
        imp.status = ProductImportStatus.failed.value
        imp.error = str(exc)
        imp.completed_at = datetime.utcnow()
        db.commit()
        return False

    imp.external_job_id = handle.external_job_id
    db.commit()
    return True  # submitted; first poll happens on the next invocation


def _poll_import(db: Session, imp: ProductImport) -> bool:
    handle = ScrapeHandle(external_job_id=imp.external_job_id)
    try:
        result = product_scraper_client.poll(handle)
    except ScrapePending:
        return True
    except Exception as exc:
        # Our own error (service unreachable, bad response, ...), not the
        # scraper reporting a failed scrape — that case is handled below,
        # once `result` actually comes back.
        imp.status = ProductImportStatus.failed.value
        imp.error = str(exc)
        imp.completed_at = datetime.utcnow()
        db.commit()
        return False

    imp.raw_result = result
    if result.get("status") != "ok":
        # The scraper reached a page and gave up cleanly (blocked,
        # not_a_product, ...) — its own message is more useful to show a
        # user than anything we'd write here.
        imp.status = ProductImportStatus.failed.value
        imp.error = result.get("message") or f"Scrape did not succeed (status: {result.get('status')})"
        imp.completed_at = datetime.utcnow()
        db.commit()
        return False

    imp.product_name = result.get("product_name") or None
    imp.product_description = result.get("product_description") or None
    imp.brand_name = result.get("brand_name") or None
    imp.price = result.get("price") or None
    imp.theme_colors = result.get("product_theme") or []

    for image_url in result.get("product_images", [])[:MAX_IMPORTED_IMAGES]:
        try:
            resp = httpx.get(image_url, timeout=15.0, follow_redirects=True)
            resp.raise_for_status()
            content = resp.content
        except Exception:
            # One bad image (dead link, hotlink-protected, ...) shouldn't
            # fail the whole import — skip it, keep the rest.
            continue

        ext = _guess_extension(image_url, resp.headers.get("content-type", ""))
        key = f"{imp.team_id}/imported/{new_id()}.{ext}"
        storage.save(key, content)
        db.add(
            Asset(
                team_id=imp.team_id,
                created_by=imp.created_by,
                kind=AssetKind.imported.value,
                media_type=MediaType.image.value,
                storage_key=key,
                url=storage.url_for(key),
                product_import_id=imp.id,
            )
        )

    imp.status = ProductImportStatus.done.value
    imp.completed_at = datetime.utcnow()
    db.commit()
    return False


class WorkerSettings:
    functions = [run_generation_job, run_product_import]
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
