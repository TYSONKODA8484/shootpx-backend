# B6 — Refine Version History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** `GET /assets/{asset_id}/versions` — a read-only reconstruction of the Refine page's "Versions" rail, walking `generation_jobs.output_asset_id -> source_asset_id` backwards.

**Architecture:** No new table — every `GenerationJob` already has `source_asset_id`/`output_asset_id`; this just queries that chain repeatedly. Starting at the given asset, repeatedly find the most recent `GenerationJob` whose `output_asset_id` is the current asset; if found, record it (labeled with that job's tool's `display_name`) and move to `job.source_asset_id`; if not found (a dead end — the original upload/import, or nothing produced it), record the asset itself as `"Original"` and stop.

**Tech Stack:** Python, FastAPI, SQLAlchemy, pytest.

---

### Task 1: `schemas/assets.py` additions

**Files:**
- Modify: `app/schemas/assets.py`

- [x] **Step 1: Add the schemas**

Append to `app/schemas/assets.py`:

```python
class AssetVersionEntry(BaseModel):
    asset_id: str
    url: str
    label: str
    created_at: str  # isoformat


class AssetVersionsOut(BaseModel):
    versions: list[AssetVersionEntry]  # ordered newest-first
```

- [x] **Step 2: Commit**

```bash
git add app/schemas/assets.py
git commit -m "feat(assets): add asset version history schemas

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `asset_controller.get_asset_versions`

**Files:**
- Modify: `app/controllers/asset_controller.py`
- Test: `tests/test_asset_versions.py`

- [x] **Step 1: Write the failing tests**

```python
"""tests/test_asset_versions.py — get_asset_versions' backward-chain walk
through generation_jobs.output_asset_id -> source_asset_id."""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.controllers import asset_controller
from app.models.asset import Asset, AssetKind
from app.models.generation_job import GenerationJob, JobStatus
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


def _make_asset(db, team, user):
    asset = Asset(
        team_id=team.id, created_by=user.id, kind=AssetKind.upload.value, media_type="image",
        storage_key=f"{team.id}/{new_id()}.png", url=f"http://x/files/{team.id}/{new_id()}.png",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _make_job(db, team, user, *, source_asset_id, output_asset_id, feature_type, completed_at):
    job = GenerationJob(
        team_id=team.id, created_by=user.id, feature_type=feature_type, status=JobStatus.done.value,
        source_asset_id=source_asset_id, output_asset_id=output_asset_id, completed_at=completed_at,
    )
    db.add(job)
    db.commit()
    return job


def _make_tool(db, feature_type, display_name):
    db.add(Tool(feature_type=feature_type, display_name=display_name, output_media_type="image"))
    db.commit()


def test_versions_of_an_untouched_asset_is_just_itself_labeled_original(db_session):
    team, user = _make_team_and_user(db_session)
    asset = _make_asset(db_session, team, user)

    result = asset_controller.get_asset_versions(db_session, asset.id, user)

    assert len(result.versions) == 1
    assert result.versions[0].asset_id == asset.id
    assert result.versions[0].label == "Original"


def test_versions_walks_the_chain_backwards_newest_first(db_session):
    team, user = _make_team_and_user(db_session)
    _make_tool(db_session, "on_model_shots", "On-Model Shots")
    _make_tool(db_session, "upscale_4k", "Upscale 4K")

    original = _make_asset(db_session, team, user)
    v2 = _make_asset(db_session, team, user)
    v3 = _make_asset(db_session, team, user)
    _make_job(db_session, team, user, source_asset_id=original.id, output_asset_id=v2.id, feature_type="on_model_shots", completed_at=T0)
    _make_job(db_session, team, user, source_asset_id=v2.id, output_asset_id=v3.id, feature_type="upscale_4k", completed_at=T0 + timedelta(minutes=5))

    result = asset_controller.get_asset_versions(db_session, v3.id, user)

    labels = [v.label for v in result.versions]
    asset_ids = [v.asset_id for v in result.versions]
    assert labels == ["Upscale 4K", "On-Model Shots", "Original"]
    assert asset_ids == [v3.id, v2.id, original.id]


def test_versions_404s_for_a_missing_asset(db_session):
    _team, user = _make_team_and_user(db_session)
    with pytest.raises(HTTPException) as exc_info:
        asset_controller.get_asset_versions(db_session, "does-not-exist", user)
    assert exc_info.value.status_code == 404


def test_versions_404s_for_a_non_member(db_session):
    team, owner = _make_team_and_user(db_session)
    _, outsider = _make_team_and_user(db_session)
    asset = _make_asset(db_session, team, owner)

    with pytest.raises(HTTPException) as exc_info:
        asset_controller.get_asset_versions(db_session, asset.id, outsider)
    assert exc_info.value.status_code == 404
```

- [x] **Step 2: Run tests to verify they fail**

Run: `./venv/Scripts/python.exe -m pytest tests/test_asset_versions.py -v`
Expected: FAIL — `AttributeError: module 'app.controllers.asset_controller' has no attribute 'get_asset_versions'`

- [x] **Step 3: Implement `get_asset_versions`**

Add this import at the top of `app/controllers/asset_controller.py`:

```python
from app.models.generation_job import GenerationJob
from app.models.tool import Tool
from app.schemas.assets import AssetListOut, AssetUpdate, AssetVersionEntry, AssetVersionsOut
```

(merge into the existing `from app.schemas.assets import ...` line rather than duplicating it)

Then append:

```python
def get_asset_versions(db: Session, asset_id: str, current_user: User) -> AssetVersionsOut:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    get_membership(db, asset.team_id, current_user.id)

    versions: list[AssetVersionEntry] = []
    current_id: str | None = asset_id
    seen: set[str] = set()  # guards against a pathological cycle

    while current_id and current_id not in seen:
        seen.add(current_id)
        current_asset = db.get(Asset, current_id)
        if current_asset is None:
            break

        job = (
            db.query(GenerationJob)
            .filter(GenerationJob.output_asset_id == current_id)
            .order_by(GenerationJob.completed_at.desc(), GenerationJob.created_at.desc())
            .first()
        )
        if job is None:
            # dead end — this asset wasn't produced by any job (the
            # original upload/import): the chain ends here.
            versions.append(AssetVersionEntry(
                asset_id=current_asset.id, url=current_asset.url, label="Original",
                created_at=current_asset.created_at.isoformat(),
            ))
            break

        tool = db.get(Tool, job.feature_type)
        label = tool.display_name if tool else job.feature_type
        versions.append(AssetVersionEntry(
            asset_id=current_asset.id, url=current_asset.url, label=label,
            created_at=(job.completed_at or job.created_at).isoformat(),
        ))
        current_id = job.source_asset_id

    return AssetVersionsOut(versions=versions)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `./venv/Scripts/python.exe -m pytest tests/test_asset_versions.py -v`
Expected: PASS (4 passed)

- [x] **Step 5: Run the full suite**

Run: `./venv/Scripts/python.exe -m pytest`
Expected: all passing

- [x] **Step 6: Commit**

```bash
git add app/controllers/asset_controller.py tests/test_asset_versions.py
git commit -m "feat(assets): add get_asset_versions controller

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Route

**Files:**
- Modify: `app/routes/asset_routes.py`

- [x] **Step 1: Add the import and route**

Add `AssetVersionsOut` to the existing `from app.schemas.assets import ...` line, then append:

```python
@router.get("/assets/{asset_id}/versions", response_model=AssetVersionsOut)
def get_asset_versions(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return asset_controller.get_asset_versions(db, asset_id, current_user)
```

- [x] **Step 2: Run the full suite**

Run: `./venv/Scripts/python.exe -m pytest`
Expected: all passing

- [x] **Step 3: Commit**

```bash
git add app/routes/asset_routes.py
git commit -m "feat(assets): add GET /assets/{asset_id}/versions route

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Manual end-to-end verification

**Files:** none (verification only)

- [x] **Step 1: Confirm the route exists**

Run: `./venv/Scripts/python.exe -m uvicorn app.main:app --port 8123` then
`curl.exe -s http://localhost:8123/openapi.json | ./venv/Scripts/python.exe -c "import json,sys; print(sorted(json.load(sys.stdin)['paths'].get('/assets/{asset_id}/versions', {}).keys()))"`
Expected: `['get']`. Stop the server (Ctrl+C) after.

---

## Self-Review Notes

- **Spec coverage:** walks `output_asset_id -> source_asset_id` backwards, labels via `Tool.display_name`, stops at a dead end labeling it `"Original"`, newest-first ordering, no new table, read-only — all covered.
- **Placeholder scan:** none.
- **Type consistency:** `get_asset_versions(db, asset_id, current_user) -> AssetVersionsOut` matches its route call and test calls; `AssetVersionEntry`/`AssetVersionsOut` field names match between schema and controller construction.
