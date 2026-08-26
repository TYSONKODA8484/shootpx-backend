# B2 — Activity Feed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** `GET /teams/{team_id}/activity` — one chronological per-team feed merging `generation_jobs` (done/failed), `product_imports` (done/failed), and curated `credit_transactions` (plan grants/top-ups/cancellations, not every generation spend).

**Architecture:** Option 1 from the design spec — a computed feed, no new table. New `schemas/activity.py`, `app/controllers/activity_controller.py`, `app/routes/activity_routes.py` (own files, same reasoning `asset_routes.py` already establishes). Each of the three source tables is queried independently (capped at `limit` rows each, filtered by an optional `before` timestamp cursor), merged and re-sorted in Python, then re-sliced to `limit`. This is an approximation, not perfect cross-stream keyset pagination — acceptable for a computed feed with no new table backing it.

**Tech Stack:** Python, FastAPI, SQLAlchemy, pytest.

---

### Task 1: `schemas/activity.py`

**Files:**
- Create: `app/schemas/activity.py`

- [x] **Step 1: Create the schema file**

```python
from pydantic import BaseModel


class ActivityEvent(BaseModel):
    id: str  # "job:<id>" | "import:<id>" | "credit:<id>" — synthetic, keeps
    # ids unique across the merged union without a real shared table.
    kind: str  # "job" | "import" | "credit"
    title: str
    detail: str
    status: str | None
    created_at: str  # isoformat
    asset_url: str | None


class ActivityFeedOut(BaseModel):
    events: list[ActivityEvent]
    next_cursor: str | None
```

- [x] **Step 2: Commit**

```bash
git add app/schemas/activity.py
git commit -m "feat(activity): add activity feed schemas

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `activity_controller.get_activity_feed`

**Files:**
- Create: `app/controllers/activity_controller.py`
- Test: `tests/test_activity_feed.py`

- [x] **Step 1: Write the failing tests**

```python
"""tests/test_activity_feed.py — GET /teams/{team_id}/activity's merge
logic: which rows from generation_jobs/product_imports/credit_transactions
show up, in what order, with what cursor.
"""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.controllers import activity_controller
from app.models.credit import CreditReason, CreditTransaction
from app.models.generation_job import GenerationJob, JobStatus
from app.models.product_import import ProductImport, ProductImportStatus
from app.models.team import Team, TeamMembership, new_id
from app.models.tool import Tool
from app.models.user import User

T0 = datetime(2026, 1, 1, 12, 0, 0)


def _make_team_and_user(db):
    team = Team(id=new_id(), name="Test Team")
    user = User(id=new_id(), email=f"{new_id()}@example.com")
    db.add_all([team, user])
    db.commit()
    db.add(TeamMembership(id=new_id(), team_id=team.id, user_id=user.id, role="owner"))
    db.commit()
    return team, user


def _job(db, team, user, *, status, created_at, feature_type="on_model_shots", error=None):
    job = GenerationJob(
        team_id=team.id, created_by=user.id, feature_type=feature_type,
        status=status, error=error, created_at=created_at,
    )
    db.add(job)
    db.commit()
    return job


def _import(db, team, user, *, status, created_at, product_name=None, source_url="https://x.example/p"):
    imp = ProductImport(
        team_id=team.id, created_by=user.id, source_url=source_url,
        status=status, product_name=product_name, created_at=created_at,
    )
    db.add(imp)
    db.commit()
    return imp


def _credit_tx(db, team, *, reason, amount, created_at):
    tx = CreditTransaction(
        team_id=team.id, amount=amount, reason=reason, balance_after=amount, created_at=created_at,
    )
    db.add(tx)
    db.commit()
    return tx


def test_feed_includes_jobs_imports_and_curated_credits_only(db_session):
    team, user = _make_team_and_user(db_session)
    _job(db_session, team, user, status=JobStatus.done.value, created_at=T0)
    _import(db_session, team, user, status=ProductImportStatus.done.value, created_at=T0)
    _credit_tx(db_session, team, reason=CreditReason.plan_grant.value, amount=100, created_at=T0)
    _credit_tx(db_session, team, reason=CreditReason.generation_spend.value, amount=-1, created_at=T0)

    feed = activity_controller.get_activity_feed(db_session, team.id, user)

    kinds = sorted(e.kind for e in feed.events)
    assert kinds == ["credit", "import", "job"]  # generation_spend excluded


def test_feed_orders_newest_first(db_session):
    team, user = _make_team_and_user(db_session)
    _job(db_session, team, user, status=JobStatus.done.value, created_at=T0)
    _job(db_session, team, user, status=JobStatus.done.value, created_at=T0 + timedelta(minutes=5))

    feed = activity_controller.get_activity_feed(db_session, team.id, user)

    assert feed.events[0].created_at > feed.events[1].created_at


def test_feed_job_title_uses_tool_display_name(db_session):
    team, user = _make_team_and_user(db_session)
    db_session.add(Tool(feature_type="on_model_shots", display_name="On-Model Shots", output_media_type="image"))
    db_session.commit()
    _job(db_session, team, user, status=JobStatus.done.value, created_at=T0, feature_type="on_model_shots")

    feed = activity_controller.get_activity_feed(db_session, team.id, user)

    assert feed.events[0].title == "On-Model Shots"


def test_feed_failed_job_detail_includes_error(db_session):
    team, user = _make_team_and_user(db_session)
    _job(db_session, team, user, status=JobStatus.failed.value, created_at=T0, error="provider timeout")

    feed = activity_controller.get_activity_feed(db_session, team.id, user)

    assert "provider timeout" in feed.events[0].detail


def test_feed_404s_for_a_non_member(db_session):
    team, _owner = _make_team_and_user(db_session)
    _, outsider = _make_team_and_user(db_session)

    with pytest.raises(HTTPException) as exc_info:
        activity_controller.get_activity_feed(db_session, team.id, outsider)
    assert exc_info.value.status_code == 404


def test_feed_pagination_cursor_walks_backwards(db_session):
    team, user = _make_team_and_user(db_session)
    _job(db_session, team, user, status=JobStatus.done.value, created_at=T0)
    _job(db_session, team, user, status=JobStatus.done.value, created_at=T0 + timedelta(minutes=5))

    page1 = activity_controller.get_activity_feed(db_session, team.id, user, limit=1)
    assert len(page1.events) == 1
    assert page1.next_cursor == page1.events[0].created_at

    page2 = activity_controller.get_activity_feed(db_session, team.id, user, limit=1, before=page1.next_cursor)
    assert len(page2.events) == 1
    assert page2.events[0].created_at < page1.events[0].created_at
```

- [x] **Step 2: Run tests to verify they fail**

Run: `./venv/Scripts/python.exe -m pytest tests/test_activity_feed.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.controllers.activity_controller'`

- [x] **Step 3: Implement `app/controllers/activity_controller.py`**

```python
"""Computed activity feed — Option 1 from the B2 design spec. No new table:
unions recent rows from generation_jobs, product_imports, and a curated
subset of credit_transactions, sorted and paginated in Python. Each source
query is capped at `limit` rows independently before the merge, so this is
an approximation of true cross-stream keyset pagination, not exact — fine
for a feed with no dedicated table backing it (see BACKEND-NEEDS.md's B2
section: "Option 1, no write path to build").
"""

from sqlalchemy.orm import Session

from app.core.asset_lookup import get_assets_cached
from app.core.permissions import get_membership
from app.models.asset import Asset
from app.models.credit import CreditReason, CreditTransaction
from app.models.generation_job import GenerationJob, JobStatus
from app.models.product_import import ProductImport, ProductImportStatus
from app.models.tool import Tool
from app.models.user import User
from app.schemas.activity import ActivityEvent, ActivityFeedOut

# Not every credit_transactions row belongs in a human-readable feed — a
# generation_spend row fires once per job and would drown out everything
# else (BACKEND-NEEDS.md's own example: "not every single generation
# deduction"). Only reasons worth surfacing as their own feed entry:
CURATED_CREDIT_REASONS = {
    CreditReason.plan_grant.value,
    CreditReason.topup_purchase.value,
    CreditReason.subscription_cancelled.value,
}


def get_activity_feed(
    db: Session,
    team_id: str,
    current_user: User,
    limit: int = 20,
    before: str | None = None,
) -> ActivityFeedOut:
    get_membership(db, team_id, current_user.id)
    limit = max(1, min(limit, 100))
    before_dt = None
    if before:
        from datetime import datetime
        before_dt = datetime.fromisoformat(before)

    job_query = db.query(GenerationJob).filter(
        GenerationJob.team_id == team_id,
        GenerationJob.status.in_([JobStatus.done.value, JobStatus.failed.value]),
    )
    if before_dt:
        job_query = job_query.filter(GenerationJob.created_at < before_dt)
    jobs = job_query.order_by(GenerationJob.created_at.desc()).limit(limit).all()

    import_query = db.query(ProductImport).filter(
        ProductImport.team_id == team_id,
        ProductImport.status.in_([ProductImportStatus.done.value, ProductImportStatus.failed.value]),
    )
    if before_dt:
        import_query = import_query.filter(ProductImport.created_at < before_dt)
    imports = import_query.order_by(ProductImport.created_at.desc()).limit(limit).all()

    credit_query = db.query(CreditTransaction).filter(
        CreditTransaction.team_id == team_id,
        CreditTransaction.reason.in_(CURATED_CREDIT_REASONS),
    )
    if before_dt:
        credit_query = credit_query.filter(CreditTransaction.created_at < before_dt)
    credits = credit_query.order_by(CreditTransaction.created_at.desc()).limit(limit).all()

    feature_types = {j.feature_type for j in jobs}
    tools_by_type = (
        {t.feature_type: t for t in db.query(Tool).filter(Tool.feature_type.in_(feature_types)).all()}
        if feature_types else {}
    )

    output_asset_ids = {j.output_asset_id for j in jobs if j.output_asset_id}
    assets_by_id = get_assets_cached(db, output_asset_ids) if output_asset_ids else {}

    import_ids = [i.id for i in imports]
    first_image_by_import: dict[str, str] = {}
    if import_ids:
        images = (
            db.query(Asset)
            .filter(Asset.product_import_id.in_(import_ids))
            .order_by(Asset.created_at.asc())
            .all()
        )
        for img in images:
            first_image_by_import.setdefault(img.product_import_id, img.url)

    events: list[ActivityEvent] = []

    for j in jobs:
        tool = tools_by_type.get(j.feature_type)
        title = tool.display_name if tool else j.feature_type
        detail = "Completed" if j.status == JobStatus.done.value else f"Failed: {j.error or 'unknown error'}"
        asset = assets_by_id.get(j.output_asset_id) if j.output_asset_id else None
        events.append(ActivityEvent(
            id=f"job:{j.id}", kind="job", title=title, detail=detail, status=j.status,
            created_at=j.created_at.isoformat(), asset_url=asset.url if asset else None,
        ))

    for i in imports:
        title = i.product_name or i.source_url
        events.append(ActivityEvent(
            id=f"import:{i.id}", kind="import", title=title, detail=i.status.capitalize(), status=i.status,
            created_at=i.created_at.isoformat(), asset_url=first_image_by_import.get(i.id),
        ))

    for c in credits:
        sign = "+" if c.amount > 0 else ""
        events.append(ActivityEvent(
            id=f"credit:{c.id}", kind="credit", title=c.reason.replace("_", " ").title(),
            detail=f"{sign}{c.amount} credits", status=None,
            created_at=c.created_at.isoformat(), asset_url=None,
        ))

    events.sort(key=lambda e: e.created_at, reverse=True)
    page = events[:limit]
    next_cursor = page[-1].created_at if len(page) == limit else None
    return ActivityFeedOut(events=page, next_cursor=next_cursor)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `./venv/Scripts/python.exe -m pytest tests/test_activity_feed.py -v`
Expected: PASS (7 passed)

- [x] **Step 5: Run the full suite**

Run: `./venv/Scripts/python.exe -m pytest`
Expected: all passing

- [x] **Step 6: Commit**

```bash
git add app/controllers/activity_controller.py tests/test_activity_feed.py
git commit -m "feat(activity): add computed activity feed controller

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Route + wire into `main.py`

**Files:**
- Create: `app/routes/activity_routes.py`
- Modify: `app/main.py`

- [x] **Step 1: Create the route**

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers import activity_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.activity import ActivityFeedOut

router = APIRouter(tags=["activity"])


@router.get("/teams/{team_id}/activity", response_model=ActivityFeedOut)
def get_activity_feed(
    team_id: str,
    limit: int = Query(default=20, le=100, gt=0),
    before: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return activity_controller.get_activity_feed(db, team_id, current_user, limit=limit, before=before)
```

- [x] **Step 2: Wire the router into `app/main.py`**

Add the import alongside the other route imports:

```python
from app.routes.activity_routes import router as activity_router
```

Add the include alongside the other `app.include_router(...)` calls (right after `app.include_router(asset_router)`):

```python
app.include_router(activity_router)
```

- [x] **Step 3: Run the full suite**

Run: `./venv/Scripts/python.exe -m pytest`
Expected: all passing

- [x] **Step 4: Commit**

```bash
git add app/routes/activity_routes.py app/main.py
git commit -m "feat(activity): add GET /teams/{team_id}/activity route

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Manual verification against the running API

**Files:** none (verification only)

- [x] **Step 1: Start the API**

Run: `./venv/Scripts/python.exe -m uvicorn app.main:app --port 8123`

- [x] **Step 2: Confirm the route exists**

Run: `curl.exe -s http://localhost:8123/openapi.json | ./venv/Scripts/python.exe -c "import json,sys; print(sorted(json.load(sys.stdin)['paths'].get('/teams/{team_id}/activity', {}).keys()))"`
Expected: `['get']`

- [x] **Step 3: Stop the server**

Ctrl+C.

---

## Self-Review Notes

- **Spec coverage:** merges all three sources, curated credit reasons (not
  `generation_spend`), synthetic per-kind ids, `before`-cursor pagination,
  `asset_url` resolution for both jobs and imports — all covered.
- **Placeholder scan:** none.
- **Type consistency:** `get_activity_feed(db, team_id, current_user, limit=20, before=None) -> ActivityFeedOut` matches its route call exactly; `ActivityEvent`/`ActivityFeedOut` field names match between schema and controller construction.
