# B1 — Asset Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /teams/{team_id}/assets` (list, with `kind`/`media_type` filters + pagination) and `DELETE /assets/{asset_id}` (real delete: file + cache + DB row) — the first real delete flow in this app, and what the Library page needs to show/remove anything.

**Architecture:** Two new controller functions in the existing `asset_controller.py`, two new routes in `asset_routes.py`, one new schema in `schemas/assets.py`. One new `Storage.delete()` method on the existing `core/storage.py` seam (`core/cache.py`'s `delete()` already exists — no change needed there, contrary to `BACKEND-NEEDS.md`'s claim). No new tables, no new migration.

**Tech Stack:** Python, FastAPI, SQLAlchemy, pytest, `unittest.mock` / `monkeypatch` for isolating the `Storage`/`cache` seams in tests (no real disk or Redis I/O in the automated suite).

---

### Task 1: `Storage.delete()`

**Files:**
- Modify: `app/core/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing test**

```python
"""tests/test_storage.py — LocalStorage.delete() behavior."""

import os

from app.core.storage import LocalStorage


def test_delete_removes_the_file(tmp_path):
    storage = LocalStorage(root_dir=str(tmp_path), base_url="http://x/files")
    storage.save("team-1/thing.png", b"hello")
    full_path = tmp_path / "team-1" / "thing.png"
    assert full_path.exists()

    storage.delete("team-1/thing.png")

    assert not full_path.exists()


def test_delete_is_a_noop_for_a_missing_file(tmp_path):
    storage = LocalStorage(root_dir=str(tmp_path), base_url="http://x/files")
    storage.delete("team-1/does-not-exist.png")  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/Scripts/python.exe -m pytest tests/test_storage.py -v`
Expected: FAIL — `AttributeError: 'LocalStorage' object has no attribute 'delete'`

- [ ] **Step 3: Implement `delete()`**

In `app/core/storage.py`, add to the `Storage` ABC (right after `url_for`):

```python
    @abstractmethod
    def delete(self, key: str) -> None: ...
```

And to `LocalStorage` (right after its `url_for`):

```python
    def delete(self, key: str) -> None:
        path = self.root_dir / key
        try:
            path.unlink()
        except FileNotFoundError:
            pass  # already gone — deleting a missing file isn't an error here
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/Scripts/python.exe -m pytest tests/test_storage.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/core/storage.py tests/test_storage.py
git commit -m "feat(storage): add Storage.delete()

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `AssetListOut` schema

**Files:**
- Modify: `app/schemas/assets.py`

- [ ] **Step 1: Add the schema**

Append to `app/schemas/assets.py`:

```python
class AssetListOut(BaseModel):
    total: int
    assets: list[AssetOut]
```

- [ ] **Step 2: Commit**

```bash
git add app/schemas/assets.py
git commit -m "feat(assets): add AssetListOut schema

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `list_assets` and `delete_asset` controller functions

**Files:**
- Modify: `app/controllers/asset_controller.py`
- Test: `tests/test_asset_library.py`

- [ ] **Step 1: Write the failing tests**

```python
"""tests/test_asset_library.py — list_assets/delete_asset controller logic.
Storage and cache are monkeypatched to plain recording stand-ins so these
tests don't need real disk or Redis — they verify the CONTROLLER's
behavior (who can see/delete what, which calls it makes), not the seams
themselves (those are covered by test_storage.py and core/cache.py already
being trusted infra).
"""

import pytest
from fastapi import HTTPException

from app.controllers import asset_controller
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import Team, TeamMembership, new_id
from app.models.user import User


def _make_team_and_user(db, role="owner"):
    team = Team(id=new_id(), name="Test Team")
    user = User(id=new_id(), email=f"{new_id()}@example.com")
    db.add_all([team, user])
    db.commit()
    db.add(TeamMembership(id=new_id(), team_id=team.id, user_id=user.id, role=role))
    db.commit()
    return team, user


def _make_asset(db, team, user, kind=AssetKind.upload.value, media_type=MediaType.image.value, key=None):
    key = key or f"{team.id}/{new_id()}.png"
    asset = Asset(
        team_id=team.id, created_by=user.id, kind=kind, media_type=media_type,
        storage_key=key, url=f"http://x/files/{key}",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def test_list_assets_returns_only_this_teams_assets(db_session):
    team_a, user_a = _make_team_and_user(db_session)
    team_b, user_b = _make_team_and_user(db_session)
    _make_asset(db_session, team_a, user_a)
    _make_asset(db_session, team_b, user_b)

    result = asset_controller.list_assets(db_session, team_a.id, user_a)

    assert result.total == 1
    assert result.assets[0].team_id == team_a.id


def test_list_assets_filters_by_kind_and_media_type(db_session):
    team, user = _make_team_and_user(db_session)
    _make_asset(db_session, team, user, kind=AssetKind.upload.value)
    _make_asset(db_session, team, user, kind=AssetKind.generated.value)

    result = asset_controller.list_assets(db_session, team.id, user, kind="generated")

    assert result.total == 1
    assert result.assets[0].kind == AssetKind.generated.value


def test_list_assets_404s_for_a_non_member(db_session):
    team, _owner = _make_team_and_user(db_session)
    _, outsider = _make_team_and_user(db_session)

    with pytest.raises(HTTPException) as exc_info:
        asset_controller.list_assets(db_session, team.id, outsider)
    assert exc_info.value.status_code == 404


def test_delete_asset_removes_row_and_calls_storage_and_cache(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    asset = _make_asset(db_session, team, user)
    asset_id, storage_key = asset.id, asset.storage_key

    deleted_keys = []
    cache_deletes = []
    monkeypatch.setattr(asset_controller.storage, "delete", lambda key: deleted_keys.append(key))
    monkeypatch.setattr(asset_controller.cache, "delete", lambda ns, key: cache_deletes.append((ns, key)))

    asset_controller.delete_asset(db_session, asset_id, user)

    assert deleted_keys == [storage_key]
    assert cache_deletes == [("media", asset_id)]
    assert db_session.get(Asset, asset_id) is None


def test_delete_asset_404s_for_missing_asset(db_session):
    _team, user = _make_team_and_user(db_session)
    with pytest.raises(HTTPException) as exc_info:
        asset_controller.delete_asset(db_session, "does-not-exist", user)
    assert exc_info.value.status_code == 404


def test_delete_asset_404s_for_a_non_member(db_session, monkeypatch):
    team, owner = _make_team_and_user(db_session)
    _, outsider = _make_team_and_user(db_session)
    asset = _make_asset(db_session, team, owner)
    monkeypatch.setattr(asset_controller.storage, "delete", lambda key: None)
    monkeypatch.setattr(asset_controller.cache, "delete", lambda ns, key: None)

    with pytest.raises(HTTPException) as exc_info:
        asset_controller.delete_asset(db_session, asset.id, outsider)
    assert exc_info.value.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/Scripts/python.exe -m pytest tests/test_asset_library.py -v`
Expected: FAIL — `AttributeError: module 'app.controllers.asset_controller' has no attribute 'list_assets'` (and `delete_asset`)

- [ ] **Step 3: Implement both functions**

In `app/controllers/asset_controller.py`, change the imports at the top from:

```python
import os

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.permissions import compute_permissions, get_membership
from app.core.storage import storage
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import new_id
from app.models.user import User
```

to:

```python
import os

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core import cache
from app.core.permissions import compute_permissions, get_membership
from app.core.storage import storage
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import new_id
from app.models.user import User
from app.schemas.assets import AssetListOut
```

Then append these two functions at the end of the file:

```python
def list_assets(
    db: Session,
    team_id: str,
    current_user: User,
    kind: str | None = None,
    media_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AssetListOut:
    get_membership(db, team_id, current_user.id)  # 404s if not a member — same
    # "don't confirm existence" pattern every other team-scoped read uses.

    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    query = db.query(Asset).filter(Asset.team_id == team_id)
    if kind:
        query = query.filter(Asset.kind == kind)
    if media_type:
        query = query.filter(Asset.media_type == media_type)

    total = query.count()
    assets = query.order_by(Asset.created_at.desc()).offset(offset).limit(limit).all()
    return AssetListOut(total=total, assets=assets)


def delete_asset(db: Session, asset_id: str, current_user: User) -> None:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    membership = get_membership(db, asset.team_id, current_user.id)
    if not compute_permissions(membership.role).can_upload_assets:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to delete assets on this team")

    storage.delete(asset.storage_key)
    cache.delete("media", asset.id)
    db.delete(asset)
    db.commit()
    # GenerationJob.output_asset_id rows pointing at this asset are left as
    # they are, on purpose — no cascade. A job stays queryable audit history
    # even after its output asset is gone; the frontend just handles a
    # 404'd image URL. See BACKEND-NEEDS.md's B1 section for the reasoning.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/Scripts/python.exe -m pytest tests/test_asset_library.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Run the full suite**

Run: `./venv/Scripts/python.exe -m pytest`
Expected: all passing (29 passed)

- [ ] **Step 6: Commit**

```bash
git add app/controllers/asset_controller.py tests/test_asset_library.py
git commit -m "feat(assets): add list_assets and delete_asset controller logic

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Routes

**Files:**
- Modify: `app/routes/asset_routes.py`

- [ ] **Step 1: Replace the file's contents**

```python
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.controllers import asset_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.assets import AssetListOut, AssetOut

router = APIRouter(tags=["assets"])


@router.post("/teams/{team_id}/assets", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    team_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await asset_controller.upload_asset(db, team_id, current_user, file)


@router.get("/teams/{team_id}/assets", response_model=AssetListOut)
def list_assets(
    team_id: str,
    kind: str | None = Query(default=None),
    media_type: str | None = Query(default=None),
    limit: int = Query(default=50, le=200, gt=0),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return asset_controller.list_assets(db, team_id, current_user, kind=kind, media_type=media_type, limit=limit, offset=offset)


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset_controller.delete_asset(db, asset_id, current_user)
```

- [ ] **Step 2: Run the full suite**

Run: `./venv/Scripts/python.exe -m pytest`
Expected: all passing

- [ ] **Step 3: Commit**

```bash
git add app/routes/asset_routes.py
git commit -m "feat(assets): add GET /teams/{team_id}/assets and DELETE /assets/{asset_id} routes

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Manual end-to-end verification against the running API

**Files:** none (verification only)

- [ ] **Step 1: Start the API**

Run: `./venv/Scripts/python.exe -m uvicorn app.main:app --port 8123`

- [ ] **Step 2: Exercise the flow via `/docs`**

Open `http://localhost:8123/docs`. Using an already-authenticated session
(see README's test-console instructions) or an existing team/asset from
manual testing:
1. `GET /teams/{team_id}/assets` — confirm it returns `{ total, assets }`
   for a team you belong to.
2. `DELETE /assets/{asset_id}` on one of them — confirm `204`, then
   `GET /teams/{team_id}/assets` again — confirm it's gone from the list
   and the file is gone from `storage/{team_id}/`.

- [ ] **Step 3: Stop the server**

Ctrl+C.

---

## Self-Review Notes

- **Spec coverage:** `Storage.delete()`, `GET /teams/{team_id}/assets`
  (kind/media_type filters, pagination), `DELETE /assets/{asset_id}`
  (storage + cache + DB, no job cascade) — all covered. `cache.delete()`
  confirmed already existing, so no task for it.
- **Placeholder scan:** none.
- **Type consistency:** `list_assets(db, team_id, current_user, kind=None, media_type=None, limit=50, offset=0) -> AssetListOut` matches its route call exactly; `delete_asset(db, asset_id, current_user) -> None` matches its route call exactly; `AssetListOut(total, assets)` matches `schemas/assets.py`'s new class.
