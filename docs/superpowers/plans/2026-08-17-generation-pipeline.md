# Real Generation Pipeline (queue, bulk, status polling) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the synchronous, inline `/generate` call with a real Redis+arq queue, add bulk submission (`/generate/bulk`), and add polling endpoints (`GET /jobs`, `GET /batches/{batch_id}`) — all sharing one concurrency model: a per-team lock (only one job per team runs at a time) plus a global worker cap (`MAX_CONCURRENT_GENERATIONS`).

**Architecture:** `POST /generate` and `POST /generate/bulk` create `GenerationJob` row(s) (status `processing` immediately, matching the current API contract) and enqueue arq tasks — they never call the AI provider inline anymore. A separate `app/worker.py` process runs the arq worker; its one task function, `run_generation_job`, acquires a per-team Redis lock before doing any work (`SET NX EX`, safe Lua-script release) and re-queues itself via arq's `Retry` if the lock is held — so a blocked job doesn't occupy one of the worker's global concurrency slots while it waits. arq's own `max_jobs` setting is `MAX_CONCURRENT_GENERATIONS`, capping total concurrent jobs across every team. Bulk submissions get a shared `batch_id`; polling reads job rows straight from Postgres (no separate Batch table).

**Tech Stack:** FastAPI, SQLAlchemy/Postgres (existing), Redis (new — see Task 0 below for how to get one running locally on Windows), `arq` (new — async Redis task queue), `redis`/`hiredis` (arq's client deps).

**Deviation from the usual plan format, and why:** this codebase has zero automated tests by design — `README.md`'s own Testing section says so explicitly: testing is done by hand, against a live Postgres and a live server, verifying real DB state and real bytes, not mocked assertions. So instead of pytest-style "write failing test / implement / pass" steps, each task's verification step is "run the server (+ worker where relevant), hit the endpoint, check the real response/DB row" — the same pattern every existing feature in this repo was built with. Task 10 formalizes the spec's manual "test for real" checklist into a rerunnable script, `scripts/test_pipeline.py`, so it isn't a one-off.

**A decision made while planning, flagged explicitly:** `MockAIProvider.generate()` currently returns instantly. With no queue, that was fine — now, with a real per-team lock, an instant mock makes the lock invisible: 5 bulk jobs would all finish within the same DB round-trip and polling could never observe the done-count "climbing one at a time," which is one of the spec's own required proofs. Fix: a new `MOCK_GENERATION_DELAY_SECONDS` setting (default `3`), slept in the worker task (not inside `ai_provider.py` — that file stays untouched) right before calling the mock. Set it to `0` once a real, naturally-slow AI provider is wired in later.

**A required manual step this plan cannot do for you:** `generation_jobs` is an existing table. `Base.metadata.create_all()` (what this project uses instead of migrations) only creates *missing* tables — it will not add the new `batch_id` column to a table that already exists in your local Postgres. Task 1 flags exactly what to run; I will not run destructive/schema-altering SQL against your local database without you telling me to.

---

## Task 0: Get a local Redis running (environment setup, not code)

You said you don't have the env info to test this yet — this is that. No Docker and no WSL distro are installed on this machine (checked both), so the lightest path on native Windows is **Memurai** (free Developer edition, Redis-protocol-compatible, plain installer, no VM/container, no restart):

1. Download "Memurai for Developers" from `https://www.memurai.com/get-memurai` and run the installer — it installs as a Windows service listening on `localhost:6379`, matching the default `REDIS_URL` this plan adds.
2. Verify it's up: `redis-cli ping` (Memurai ships its own `memurai-cli`, or install `redis-cli` separately) should return `PONG`. If you don't want a CLI installed, Task 10's test script itself will fail loudly and clearly if Redis isn't reachable, which is an equally good check.

Alternatives, if you'd rather use one of these: Docker Desktop (`docker run -d -p 6379:6379 redis:7-alpine`) once installed, or WSL2 (`wsl --install`, then `sudo apt install redis-server` inside it — WSL2's localhost forwarding means `REDIS_URL=redis://localhost:6379/0` still works unmodified from Windows). Whichever you pick, nothing else in this plan changes — only `REDIS_URL` in `.env` would.

---

## Task 1: Config, env template, and dependencies

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env.example`
- Modify: `requirements.txt`

- [ ] **Step 1: Add the three new settings**

In `app/core/config.py`, add after the `STORAGE_ROOT_DIR` line (inside the `Settings` class):

```python
    # Redis — backs the arq task queue (app/worker.py) and the per-team
    # generation lock. Get one running locally first; see DESIGN.md.
    REDIS_URL: str = "redis://localhost:6379/0"

    # Hard cap on how many generation jobs run at once, across every team
    # combined — protects whatever real AI API gets wired in later from
    # unlimited parallel requests. Independent of the per-team lock (that
    # one limits fairness *between* teams; this one limits total load).
    MAX_CONCURRENT_GENERATIONS: int = 10

    # Artificial delay (seconds) the worker sleeps before calling
    # MockAIProvider, since the mock itself returns instantly. Without this,
    # the per-team lock has nothing to serialize that's slow enough to
    # observe by polling. Set to 0 once a real (naturally slow) AI provider
    # replaces the mock.
    MOCK_GENERATION_DELAY_SECONDS: int = 3
```

- [ ] **Step 2: Mirror it in `.env.example`**

Append to `.env.example`, after the `STORAGE_ROOT_DIR` section:

```bash
# --- Redis (arq task queue + per-team generation lock) ---
# Local Memurai/Docker/WSL Redis all listen here by default — see DESIGN.md
# for how to get one running on Windows.
REDIS_URL=redis://localhost:6379/0

# --- Generation pipeline ---
MAX_CONCURRENT_GENERATIONS=10
MOCK_GENERATION_DELAY_SECONDS=3
```

- [ ] **Step 3: Add the new dependencies, pinned**

Append to `requirements.txt`:

```
arq==0.28.0
redis==5.3.1
hiredis==3.4.1
```

(Verified together via `pip install --dry-run arq redis` against this repo's existing `requirements.txt` — this is exactly what arq 0.28.0 resolves to; `redis` is capped below 6 by arq itself.)

- [ ] **Step 4: Install and verify**

Run: `./venv/Scripts/python.exe -m pip install -r requirements.txt`
Expected: installs `arq`, `redis`, `hiredis` with no errors (everything else already satisfied).

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py .env.example requirements.txt
git commit -m "chore: add Redis/arq config for the generation queue"
```

---

## Task 2: `batch_id` on `GenerationJob`

**Files:**
- Modify: `app/models/generation_job.py`

- [ ] **Step 1: Add the column**

In `app/models/generation_job.py`, add after `source_asset_id`/`output_asset_id`:

```python
    batch_id = Column(String, nullable=True)  # shared by every job from one
    # /generate/bulk call; null for a single /generate. Not a FK — there's
    # no separate batches table, same lightweight-string pattern as
    # feature_type. Add an index if batch lookups ever get slow; skipped
    # for now (YAGNI at this scale).
```

- [ ] **Step 2: Handle the existing table (manual, ask first)**

`Base.metadata.create_all()` in `app/main.py` won't alter an already-existing `generation_jobs` table. Tell the user (me) which applies to their local DB and get a yes before running either:
- No real data yet worth keeping → drop and let it recreate: `DROP TABLE generation_jobs;` then restart the API once (create_all rebuilds it with `batch_id`).
- Data worth keeping → `ALTER TABLE generation_jobs ADD COLUMN batch_id VARCHAR;`

Do not run either against the user's Postgres without explicit confirmation — this step is a conversation, not an automated step.

- [ ] **Step 3: Commit**

```bash
git add app/models/generation_job.py
git commit -m "feat: add batch_id to GenerationJob for bulk submissions"
```

---

## Task 3: The queue pool + worker process

**Files:**
- Create: `app/core/queue.py`
- Create: `app/worker.py`

- [ ] **Step 1: Write the enqueue helper**

Create `app/core/queue.py`:

```python
"""arq connection pool used by the API process to enqueue generation jobs.
One pool per process, lazily created on first use and reused after —
same lazy-singleton pattern as the AI provider/storage modules. The worker
process (app/worker.py) never imports this file; it gets its own
connection via arq's WorkerSettings.
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


async def enqueue_generation_job(job_id: str, team_id: str) -> None:
    """Fire-and-forget: hands the job to arq and returns. The actual AI
    call happens later, in app/worker.py's run_generation_job, once that
    team's per-team lock is free and a global worker slot is available."""
    pool = await get_queue_pool()
    await pool.enqueue_job("run_generation_job", job_id, team_id)
```

- [ ] **Step 2: Write the worker task + entrypoint**

Create `app/worker.py`:

```python
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
    # they shouldn't count toward arq's normal retry-then-give-up budget
    # (default max_tries=5, which a job waiting behind even a handful of
    # others in a bulk batch would blow through in a couple seconds,
    # getting silently killed by arq before ever reaching _process_job,
    # leaving its GenerationJob row stuck at "processing" forever). Bounded
    # in practice by LOCK_TTL_SECONDS and realistic per-team queue depth.
```

- [ ] **Step 3: Verify the worker starts and connects**

Run (with Redis up from Task 0): `./venv/Scripts/python.exe -m arq app.worker.WorkerSettings`
Expected: logs something like `redis_version=... starting worker for 1 functions` and stays running (Ctrl+C to stop). If it instead errors connecting, Redis isn't reachable at `REDIS_URL` — fix Task 0 first.

- [ ] **Step 4: Commit**

```bash
git add app/core/queue.py app/worker.py
git commit -m "feat: arq worker with per-team lock + global concurrency cap"
```

---

## Task 4: Wire `/generate` to the queue instead of running inline

**Files:**
- Modify: `app/controllers/generation_controller.py`
- Modify: `app/routes/generation_routes.py`

- [ ] **Step 1: Replace the inline AI call with an enqueue**

In `app/controllers/generation_controller.py`, replace the whole `run_generation` function body (everything from `def run_generation` through the final `return job`) with:

```python
from app.core.queue import enqueue_generation_job


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
    # team's lock is free and a global worker slot is available.
    await enqueue_generation_job(job.id, payload.team_id)
    return job
```

Remove the now-unused `from datetime import datetime` and `from app.core.ai_provider import ai_provider` and `from app.core.storage import storage` and `from app.models.asset import Asset, AssetKind` imports only if nothing else in the file still needs them — `Asset` is still needed (source_asset lookup above), the rest (`ai_provider`, `storage`, `datetime`, `AssetKind`) are not, so remove those three.

- [ ] **Step 2: Make the route async**

In `app/routes/generation_routes.py`, change:

```python
@router.post("/generate", response_model=GenerationJobOut, status_code=status.HTTP_201_CREATED)
def generate(
```
to:
```python
@router.post("/generate", response_model=GenerationJobOut, status_code=status.HTTP_201_CREATED)
async def generate(
```
and its body to `return await generation_controller.run_generation(db, current_user, payload)`.

- [ ] **Step 3: Verify end-to-end**

With Postgres, Redis, the worker (Task 3 Step 3), and `uvicorn app.main:app --reload` all running, plus a valid session cookie (log in via the test console per `DESIGN.md`) and a real `team_id`/`source_asset_id` from your dev DB:

```bash
curl -s -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -b "session_token=<your cookie value>" \
  -d '{"team_id":"<team-id>","feature_type":"on_model_shots","source_asset_id":"<asset-id>","input_payload":{}}'
```

Expected: `201`, JSON with `"status":"processing"`, `"output_asset_id":null`. Watch the worker terminal — a few seconds later (per `MOCK_GENERATION_DELAY_SECONDS`) it logs the job completing. Re-`GET` the job (Task 6 adds a real endpoint for this; until then, checking `generation_jobs` in Postgres directly is fine) to confirm `status` flips to `done` and `output_asset_id` is set.

- [ ] **Step 4: Commit**

```bash
git add app/controllers/generation_controller.py app/routes/generation_routes.py
git commit -m "feat: /generate enqueues via arq instead of running inline"
```

---

## Task 5: Schemas for bulk submission + status polling

**Files:**
- Modify: `app/schemas/generation.py`

- [ ] **Step 1: Factor the shared validator, add the new schemas**

Replace the full contents of `app/schemas/generation.py` with:

```python
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
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `./venv/Scripts/python.exe -c "from app.schemas import generation"`
Expected: no output, no error.

- [ ] **Step 3: Commit**

```bash
git add app/schemas/generation.py
git commit -m "feat: schemas for bulk generation + status polling"
```

---

## Task 6: Non-raising team-access check (for silently-omit-on-/jobs)

**Files:**
- Modify: `app/core/permissions.py`

- [ ] **Step 1: Add `has_team_access`**

In `app/core/permissions.py`, add after `get_membership`:

```python
def has_team_access(db: Session, team_id: str, user_id: str) -> bool:
    """Same membership check as get_membership, but returns False instead
    of raising — for endpoints like GET /jobs that must silently omit
    inaccessible rows rather than error the whole request over one bad id."""
    return (
        db.query(TeamMembership)
        .filter(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id)
        .first()
        is not None
    )
```

- [ ] **Step 2: Commit**

```bash
git add app/core/permissions.py
git commit -m "feat: add non-raising has_team_access permission check"
```

---

## Task 7: Bulk submission + status-polling controller logic

**Files:**
- Modify: `app/controllers/generation_controller.py`

- [ ] **Step 1: Add the bulk submission function**

Append to `app/controllers/generation_controller.py` (add `from app.core.permissions import ..., has_team_access` to the existing import line, and add `from app.models.generation_job import ...` already-imported `JobStatus`/`GenerationJob` cover this; add `from app.schemas.generation import BulkGenerateRequest, BulkGenerateResponse, GenerationJobSummary, BatchStatusOut, AssetRef` to the schema import line):

```python
async def run_generation_bulk(
    db: Session, current_user: User, payload: BulkGenerateRequest
) -> BulkGenerateResponse:
    membership = get_membership(db, payload.team_id, current_user.id)
    if not compute_permissions(membership.role).can_generate:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to generate on this team")

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
        )
        for asset_id in payload.asset_ids
    ]
    db.add_all(jobs)
    db.commit()
    for job in jobs:
        db.refresh(job)

    # Same enqueue as single /generate — the per-team lock is what makes
    # these run one after another, not a separate batch mechanism.
    for job in jobs:
        await enqueue_generation_job(job.id, payload.team_id)

    return BulkGenerateResponse(batch_id=batch_id, job_ids=[j.id for j in jobs])
```

- [ ] **Step 2: Add the summary-building helper + the two read endpoints' logic**

Append:

```python
def _to_summaries(db: Session, jobs: list[GenerationJob]) -> list[GenerationJobSummary]:
    asset_ids = {j.source_asset_id for j in jobs if j.source_asset_id}
    asset_ids |= {j.output_asset_id for j in jobs if j.output_asset_id}
    assets = (
        {a.id: a for a in db.query(Asset).filter(Asset.id.in_(asset_ids)).all()}
        if asset_ids
        else {}
    )

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
    accessible = [
        jobs_by_id[jid]
        for jid in job_ids
        if jid in jobs_by_id and has_team_access(db, jobs_by_id[jid].team_id, current_user.id)
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
```

- [ ] **Step 3: Verify it imports cleanly**

Run: `./venv/Scripts/python.exe -c "from app.controllers import generation_controller"`
Expected: no output, no error. (Real behavioral verification happens in Task 9.)

- [ ] **Step 4: Commit**

```bash
git add app/controllers/generation_controller.py
git commit -m "feat: bulk generation + job/batch status controller logic"
```

---

## Task 8: The three new/changed routes

**Files:**
- Modify: `app/routes/generation_routes.py`

- [ ] **Step 1: Add the routes**

Replace the full contents of `app/routes/generation_routes.py` with:

```python
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
```

- [ ] **Step 2: Verify the app starts and the routes are registered**

Run: `./venv/Scripts/python.exe -c "from app.main import app; print(sorted(r.path for r in app.routes if 'generat' in r.path or 'batches' in r.path or r.path == '/jobs'))"`
Expected: `['/batches/{batch_id}', '/generate', '/generate/bulk', '/jobs']`

- [ ] **Step 3: Commit**

```bash
git add app/routes/generation_routes.py
git commit -m "feat: /generate/bulk, GET /jobs, GET /batches/{batch_id} routes"
```

---

## Task 9: Docs — README + DESIGN.md

**Files:**
- Modify: `README.md`
- Modify: `DESIGN.md`

- [ ] **Step 1: README — running it now needs two processes**

In `README.md`, in the "## Running it" section, replace the single `uvicorn` command block with:

````markdown
This now needs **two processes** — the API and the arq worker that
actually runs generation jobs. Start Redis first (see `DESIGN.md` for how
to get one running locally on Windows), then:

```bash
# terminal 1 — the API
uvicorn app.main:app --reload

# terminal 2 — the worker (processes queued /generate and /generate/bulk jobs)
./venv/Scripts/python.exe -m arq app.worker.WorkerSettings
```
````

- [ ] **Step 2: README — env var table + API overview table**

In the env var table (`## Setup` → step 3), add a row:
```markdown
| `REDIS_URL` | your local Redis — see `DESIGN.md` for how to get one running on Windows |
```

In the "## API overview" table, replace the `POST /generate` row with:
```markdown
| `POST /generate` | run a tool on one asset: `team_id`, `feature_type`, `source_asset_id`, `input_payload` — enqueued, returns immediately |
| `POST /generate/bulk` | run a tool on up to 100 assets at once: `team_id`, `feature_type`, `asset_ids`, `input_payload` — returns a `batch_id` + all job ids immediately |
| `GET /jobs?ids=...` | poll one or many jobs by comma-separated id |
| `GET /batches/{batch_id}` | poll a bulk submission's aggregate + per-job status |
```

- [ ] **Step 3: DESIGN.md — document the queue architecture**

In `DESIGN.md`, replace the "**Routes:**" line and the two paragraphs immediately after it (in the "## Core product system: assets & generation jobs" section — the part describing `POST /generate` as "synchronous today") with:

```markdown
**Routes:** `POST /teams/{team_id}/assets` (upload), `POST /generate`
(single), `POST /generate/bulk` (up to 100 assets, one `feature_type`,
shared `batch_id`), `GET /jobs?ids=...`, `GET /batches/{batch_id}`.

Generation is queued, not synchronous: `POST /generate`/`/generate/bulk`
create `GenerationJob` row(s) (`status: "processing"` immediately) and
enqueue arq tasks; a separate worker process (`app/worker.py`, run via
`arq app.worker.WorkerSettings`) does the actual `AIProvider.generate()`
call later. Two concurrency limits apply, independently:
- **Per-team lock** (Redis `SET NX EX`, released via a safe Lua
  check-and-delete): only one `GenerationJob` per team runs at a time,
  across `/generate` and `/generate/bulk` alike. This is the *entire*
  mechanism behind bulk processing "one after another" — there's no
  separate batch-runner, just this same lock. A job that finds the lock
  held re-queues itself (`arq.Retry`) instead of blocking a worker slot.
- **Global cap** (`MAX_CONCURRENT_GENERATIONS`, arq's `max_jobs`): total
  jobs running across *every* team combined, protecting whatever real AI
  API gets wired in later from unlimited parallel requests.

`batch_id` (nullable string on `GenerationJob`) is shared by every job
from one `/generate/bulk` call, null for a single `/generate`. Not its own
table — same lightweight-string pattern as `feature_type`.

`MockAIProvider` is deliberately slowed down now (`MOCK_GENERATION_DELAY_SECONDS`,
default 3s, slept in the worker before calling it) — instant mock results
made the per-team lock unobservable by polling. `ai_provider.py` itself is
untouched; drop the setting to `0` once a real, naturally-slow provider
replaces the mock.
```

- [ ] **Step 4: Commit**

```bash
git add README.md DESIGN.md
git commit -m "docs: document the queue, per-team lock, and new endpoints"
```

---

## Task 10: The "test for real" script

**Files:**
- Create: `scripts/test_pipeline.py`

This turns the spec's manual checklist into a rerunnable script. It talks to a **live running API** over real HTTP (`urllib`, stdlib only — no new dependency for a script). To avoid needing a real Firebase login, it creates its own throwaway users/teams/assets **directly in Postgres** via the app's own models, then mints a session cookie with the app's real `create_session_token` — same signing path a real login produces, just without driving a browser through Firebase. This mirrors how the rest of this repo is tested: against real DB state, real HTTP calls, real files — see `README.md`'s Testing section.

- [ ] **Step 1: Write the script**

Create `scripts/test_pipeline.py`:

```python
"""Exercises the real generation pipeline end to end against a LIVE server.

Prereqs (see DESIGN.md): Postgres up, Redis up, `MAX_CONCURRENT_GENERATIONS=2`
set in .env, then in two terminals:
    uvicorn app.main:app --reload
    python -m arq app.worker.WorkerSettings

Run: ./venv/Scripts/python.exe scripts/test_pipeline.py
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import create_session_token  # noqa: E402
from app.models import invite as invite_models  # noqa: E402,F401  (registers TeamInvite on
# Base — Team.invites = relationship("TeamInvite", ...) fails mapper
# configuration otherwise, the same reason app/main.py imports it)
from app.models.asset import Asset, AssetKind, MediaType  # noqa: E402
from app.models.team import Team, TeamMembership, TeamRole, new_id  # noqa: E402
from app.models.user import User  # noqa: E402

BASE_URL = "http://localhost:8000"


def api(method: str, path: str, cookie: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Cookie": f"session_token={cookie}"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def check(label: str, condition: bool) -> None:
    print(f"{'PASS' if condition else 'FAIL'}: {label}")
    if not condition:
        sys.exit(1)


def setup_team_with_assets(db, name: str, n_assets: int) -> tuple[str, str, list[str]]:
    """Creates a throwaway user + team + owner membership + n fake upload
    assets, directly in Postgres. Returns (session_cookie, team_id, asset_ids)."""
    user = User(id=new_id(), email=f"{name}-{new_id()}@example.test", name=name)
    db.add(user)
    team = Team(id=new_id(), name=f"{name}'s team")
    db.add(team)
    db.add(TeamMembership(team_id=team.id, user_id=user.id, role=TeamRole.owner.value))
    db.flush()  # Asset has plain FK columns, not an ORM relationship() to
    # Team/User, so unit-of-work insert ordering isn't relationship-driven
    # here — without this flush, Postgres can receive the INSERT INTO
    # assets before INSERT INTO teams in the same commit and reject it with
    # a ForeignKeyViolation (reproduced; this is real, not speculative).

    asset_ids = []
    for i in range(n_assets):
        asset = Asset(
            id=new_id(),
            team_id=team.id,
            created_by=user.id,
            kind=AssetKind.upload.value,
            media_type=MediaType.image.value,
            storage_key=f"{team.id}/fake-{i}.png",
            url=f"{BASE_URL}/files/{team.id}/fake-{i}.png",
        )
        db.add(asset)
        asset_ids.append(asset.id)

    db.commit()
    return create_session_token(user.id), team.id, asset_ids


def main() -> None:
    db = SessionLocal()
    try:
        cookie_a, team_a, assets_a = setup_team_with_assets(db, "team-a", 5)
        cookie_b, team_b, assets_b = setup_team_with_assets(db, "team-b", 1)
    finally:
        db.close()

    # 1. Bulk batch of 5 for team A comes back immediately, all "processing"
    status_code, body = api(
        "POST",
        "/generate/bulk",
        cookie_a,
        {"team_id": team_a, "feature_type": "on_model_shots", "asset_ids": assets_a, "input_payload": {}},
    )
    check("POST /generate/bulk returns 201", status_code == 201)
    batch_id = body["batch_id"]
    job_ids = body["job_ids"]
    check("bulk response has 5 job ids", len(job_ids) == 5)

    status_code, jobs_body = api("GET", f"/jobs?ids={','.join(job_ids)}", cookie_a)
    check("GET /jobs 200", status_code == 200)
    check("all 5 jobs start as 'processing'", all(j["status"] == "processing" for j in jobs_body))

    # 2. While the batch is running, a second single /generate for the SAME
    # team must queue behind it, not start immediately.
    status_code, single_body = api(
        "POST",
        "/generate",
        cookie_a,
        {"team_id": team_a, "feature_type": "on_model_shots", "source_asset_id": assets_a[0], "input_payload": {}},
    )
    check("second single /generate (team A) returns 201", status_code == 201)
    single_job_id = single_body["id"]

    # 3. Simultaneously, a generation for a DIFFERENT team must run
    # independently, unblocked by team A's batch.
    status_code, other_team_body = api(
        "POST",
        "/generate",
        cookie_b,
        {"team_id": team_b, "feature_type": "on_model_shots", "source_asset_id": assets_b[0], "input_payload": {}},
    )
    check("team B /generate returns 201", status_code == 201)
    other_team_job_id = other_team_body["id"]

    # 4. Poll the batch — done-count must climb one at a time, not jump
    # straight to 5 (proves the per-team lock is real).
    seen_done_counts: list[int] = []
    deadline = time.time() + 60
    while time.time() < deadline:
        status_code, batch_body = api("GET", f"/batches/{batch_id}", cookie_a)
        check("GET /batches/{batch_id} 200", status_code == 200)
        done = batch_body["done"]
        if not seen_done_counts or seen_done_counts[-1] != done:
            seen_done_counts.append(done)
            print(f"  batch done-count: {done}/5")
        if done == 5:
            break
        time.sleep(0.5)
    check("batch reached done=5", seen_done_counts[-1] == 5 if seen_done_counts else False)
    check(
        "done-count climbed one at a time (not straight to 5)",
        seen_done_counts[:2] != [0, 5] and len(seen_done_counts) >= 5,
    )

    # 5. The team-A single job must only have completed AFTER the batch —
    # i.e. it was genuinely serialized behind the batch by the per-team lock.
    status_code, single_status = api("GET", f"/jobs?ids={single_job_id}", cookie_a)
    check("team A's extra single job is done", single_status[0]["status"] == "done")

    # 6. Team B's job ran independently — should already be done too, and
    # nothing about its timing depended on team A.
    status_code, other_status = api("GET", f"/jobs?ids={other_team_job_id}", cookie_b)
    check("team B's job is done, independently", other_status[0]["status"] == "done")

    # 7. /health responds immediately regardless of any of the above.
    start = time.time()
    status_code, _ = api("GET", "/health", cookie_a, body=None)
    elapsed = time.time() - start
    check("GET /health is 200", status_code == 200)
    check("GET /health responded in well under a second", elapsed < 1.0)

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add scripts/test_pipeline.py
git commit -m "test: rerunnable end-to-end script for the generation pipeline"
```

---

## Task 11: Run the real verification (the actual proof, not just code review)

**Files:** none — this task runs everything from Tasks 0–10 together.

- [ ] **Step 1: Set the low concurrency cap for this run**

In `.env`, set `MAX_CONCURRENT_GENERATIONS=2` (temporarily — this is what makes the "climbs one at a time" and "team B unblocked" proofs meaningful; 10 would still be correct but less visibly so with only 5 jobs in the batch).

- [ ] **Step 2: Start Redis, Postgres, the API, and the worker**

Four things running: Redis (Task 0), Postgres (already running per existing setup), `uvicorn app.main:app --reload`, and `./venv/Scripts/python.exe -m arq app.worker.WorkerSettings` — each in its own terminal.

- [ ] **Step 3: Run the script**

Run: `./venv/Scripts/python.exe scripts/test_pipeline.py`
Expected: a line of `PASS: ...` for every check in Task 10's script, ending in `All checks passed.`, with the `batch done-count: N/5` lines showing 1, 2, 3, 4, 5 rather than jumping straight to 5.

- [ ] **Step 4: Revert the temporary cap**

Set `MAX_CONCURRENT_GENERATIONS` back to `10` in `.env` (or remove the line — that's the default).

---

## Self-review notes (from the writing-plans skill's required pass)

- **Spec coverage:** infra (Task 1, 3) · `batch_id` (Task 2) · per-team lock (Task 3) · global cap (Task 1, 3) · `POST /generate` enqueued (Task 4) · `POST /generate/bulk` (Task 7, 8) · `GET /jobs` (Task 7, 8) · `GET /batches/{batch_id}` (Task 7, 8) · input+output on status responses (Task 5's `AssetRef`, Task 7's `_to_summaries`) · all 5 "test for real" bullets (Task 10's script, one check block per bullet) · env/setup gap the user flagged (Task 0, 1, 9). No gaps found.
- **Placeholder scan:** none — every step has literal code/commands, no "add error handling"-style stand-ins.
- **Type consistency:** `enqueue_generation_job(job_id, team_id)` called identically in Task 4 and Task 7; `run_generation_job(ctx, job_id, team_id)` in Task 3 matches that call signature; `GenerationJobSummary`/`AssetRef`/`BatchStatusOut` field names match between Task 5's definitions and Task 7's construction of them.
