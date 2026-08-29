# On-Model Shots + Catalog Photoshoot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `on_model_shots`'s mock provider with a real fal.ai-backed implementation, add a brand-new `catalog_photoshoot` tool the same way, move both tools' model ids and system prompts out of code into DB-editable config (JSON fallback for a DB-less laptop), and fix the generation lock so a team's members don't block each other.

**Architecture:** Each tool splits into fast synchronous pre-steps (model image / prompt planning — LLM calls only) followed by N ordinary, unmodified `/generate` jobs (one per output image), so `worker.py`, `AIProvider`'s interface, and the job table need zero changes. A new `FalImageEditProvider` (one class, two configured instances) handles the actual per-image fal.ai submit/poll. A new `tool_config` DB table (JSON blob per `feature_type`, CMS-editable) with a checked-in JSON fallback file per tool holds every model id and system prompt. A separate, small fix changes the existing per-team generation lock to per-user.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, arq/Redis, `fal-client` (new), `httpx`, pytest.

**Specs this plan implements:**
- `docs/superpowers/specs/2026-08-29-on-model-shots-real-provider-design.md`
- `docs/superpowers/specs/2026-08-29-catalog-photoshoot-tool-design.md`

**Already done (previous session, before this plan):**
- `app/tools/on_model_shots_config.json` and `app/tools/catalog_photoshoot_config.json` exist and are committed, with real seeded model ids and system prompts.
- `alembic/versions/5c0e6cbe2b23_add_tool_config_table.py` exists as an empty scaffold (chained to head `e4a71be58f78`) — Task 2 fills in its body.
- `fal-client==1.0.1` is already installed in the project venv (confirmed working; Task 1 just records it in `requirements.txt`).

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `requirements.txt` | Modify | Add `fal-client`. |
| `app/models/tool_config.py` | Create | `ToolConfig` table. |
| `alembic/versions/5c0e6cbe2b23_add_tool_config_table.py` | Modify | Fill in `upgrade`/`downgrade`. |
| `app/main.py` | Modify | Register `ToolConfig` on `Base`; include the 2 new routers. |
| `app/core/cms_registry.py` | Modify | CMS-editable `tool_config` entity. |
| `app/core/tool_config.py` | Create | `load_tool_config()` — shared DB-else-JSON loader. |
| `app/core/fal_provider.py` | Create | `FalImageEditProvider(AIProvider)` — generic fal submit/poll. |
| `app/core/queue.py` | Modify | `enqueue_generation_job` gains `created_by`. |
| `app/controllers/generation_controller.py` | Modify | Pass `current_user.id` through at both enqueue call sites. |
| `app/worker.py` | Modify | Per-team lock → per-user lock. |
| `app/tools/on_model_shots.py` | Modify | Real port of `flow.py`'s logic; registers `FalImageEditProvider`. |
| `app/schemas/on_model_shots.py` | Create | Request/response models for the 2 new endpoints. |
| `app/controllers/on_model_shots_controller.py` | Create | Model-image + prompts step logic. |
| `app/routes/on_model_shots_routes.py` | Create | The 2 new routes. |
| `app/tools/catalog_photoshoot.py` | Create | Real port of `catalog_flow.py`'s logic; registers `FalImageEditProvider`. |
| `app/schemas/catalog_photoshoot.py` | Create | Request/response model for the 1 new endpoint. |
| `app/controllers/catalog_photoshoot_controller.py` | Create | Shots step logic. |
| `app/routes/catalog_photoshoot_routes.py` | Create | The 1 new route. |

Tests, one file per file above that has logic (pure functions get real assertions; every fal/VLM/HTTP call is monkeypatched — no real fal.ai call runs in the test suite):

`tests/test_tool_config.py`, `tests/test_fal_provider.py`, `tests/test_generation_lock_plumbing.py`, `tests/test_worker_lock_key.py`, `tests/test_on_model_shots_tool.py`, `tests/test_on_model_shots_controller.py`, `tests/test_catalog_photoshoot_tool.py`, `tests/test_catalog_photoshoot_controller.py`.

---

## Task 1: Add the `fal-client` dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add the pinned dependency**

Add this line to `requirements.txt`, anywhere after `httpx==0.27.2` (alongside the other HTTP-ish deps):

```
fal-client==1.0.1
```

- [ ] **Step 2: Confirm it's importable**

Run: `python -c "import fal_client; print(fal_client.version_tuple)"`
Expected: prints a version tuple, no `ImportError` (it's already installed in this venv from prep work — this just confirms it, `pip install -r requirements.txt` is what a fresh machine would run).

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add fal-client dependency"
```

---

## Task 2: `ToolConfig` table

**Files:**
- Create: `app/models/tool_config.py`
- Modify: `alembic/versions/5c0e6cbe2b23_add_tool_config_table.py`
- Modify: `app/main.py`
- Modify: `app/core/cms_registry.py`

- [ ] **Step 1: Write the model**

`app/models/tool_config.py`:

```python
from sqlalchemy import JSON, Column, DateTime, String

from app.core.db import Base
from app.core.time import utc_now


class ToolConfig(Base):
    """DB override for a tool's models/prompts. app/core/tool_config.py's
    load_tool_config() reads this first, falling back to a checked-in JSON
    file (app/tools/<feature_type>_config.json) when no row exists here or
    the DB isn't reachable at all — see
    docs/superpowers/specs/2026-08-29-on-model-shots-real-provider-design.md's
    "DB-backed models + prompts, JSON fallback" section. One row per
    feature_type; config_json's shape is entirely up to that tool's own
    file (app/tools/<feature_type>.py), not enforced here."""

    __tablename__ = "tool_config"

    feature_type = Column(String, primary_key=True)
    config_json = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
```

- [ ] **Step 2: Fill in the migration**

Replace the contents of `alembic/versions/5c0e6cbe2b23_add_tool_config_table.py`'s `upgrade`/`downgrade` functions (keep the header/revision lines exactly as they are):

```python
def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'tool_config',
        sa.Column('feature_type', sa.String(), nullable=False),
        sa.Column('config_json', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('feature_type'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('tool_config')
```

- [ ] **Step 3: Register the model in `app/main.py`**

In `app/main.py`, add this import in alphabetical position (right after the `tool` import, before `user`):

```python
from app.models import tool_config as tool_config_models  # noqa: F401  (registers ToolConfig on Base)
```

- [ ] **Step 4: Register the CMS entity**

In `app/core/cms_registry.py`, add the import in alphabetical position (right after `from app.models.tool import Tool`):

```python
from app.models.tool_config import ToolConfig
```

Then append this at the end of the file:

```python
register(EntityConfig(
    name="tool-config",
    label="Tool Config",
    model=ToolConfig,
    pk_field="feature_type",
    pk_provided_on_create=True,  # no DB default on feature_type
    search_fields=["feature_type"],
    fields=[
        FieldConfig("feature_type", "string", editable=False),
        FieldConfig("config_json", "json", help_text=(
            "Models + system prompts for this tool. See "
            "app/tools/<feature_type>_config.json for the fallback shape "
            "used when this row doesn't exist or the DB isn't reachable."
        )),
        _UPDATED_AT,
    ],
))
```

- [ ] **Step 5: Verify it migrates cleanly against the test DB**

Run: `pytest tests/test_cms_registry.py -v`
Expected: PASS (this file already asserts every registered entity's `model`/`pk_field` are internally consistent — it'll now also cover `tool-config`).

- [ ] **Step 6: Commit**

```bash
git add app/models/tool_config.py alembic/versions/5c0e6cbe2b23_add_tool_config_table.py app/main.py app/core/cms_registry.py
git commit -m "feat: add tool_config table, CMS-editable"
```

---

## Task 3: Shared config loader

**Files:**
- Create: `app/core/tool_config.py`
- Test: `tests/test_tool_config.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_tool_config.py`:

```python
"""app/core/tool_config.py's load_tool_config() — DB row first, checked-in
JSON file as the fallback when no row exists or the DB isn't reachable.
Whole-blob fallback, not per-key merging — see
docs/superpowers/specs/2026-08-29-on-model-shots-real-provider-design.md."""

import json

from app.core.tool_config import load_tool_config
from app.models.tool_config import ToolConfig


def test_load_tool_config_uses_db_row_when_present(db_session, tmp_path):
    db_session.add(ToolConfig(feature_type="on_model_shots", config_json={"models": {"a": "from-db"}}))
    db_session.commit()

    fallback = tmp_path / "fallback.json"
    fallback.write_text(json.dumps({"models": {"a": "from-json"}}))

    config = load_tool_config(db_session, "on_model_shots", fallback)
    assert config["models"]["a"] == "from-db"


def test_load_tool_config_falls_back_to_json_when_no_row(db_session, tmp_path):
    fallback = tmp_path / "fallback.json"
    fallback.write_text(json.dumps({"models": {"a": "from-json"}}))

    config = load_tool_config(db_session, "on_model_shots", fallback)
    assert config["models"]["a"] == "from-json"


def test_load_tool_config_falls_back_to_json_when_db_raises(monkeypatch, db_session, tmp_path):
    def _raise(*a, **k):
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(db_session, "get", _raise)
    fallback = tmp_path / "fallback.json"
    fallback.write_text(json.dumps({"models": {"a": "from-json"}}))

    config = load_tool_config(db_session, "on_model_shots", fallback)
    assert config["models"]["a"] == "from-json"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_tool_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.tool_config'`

- [ ] **Step 3: Implement**

`app/core/tool_config.py`:

```python
"""load_tool_config() — the DB-row-else-JSON-file loader shared by every
tool that keeps its models/prompts out of code (on_model_shots.py,
catalog_photoshoot.py — see docs/superpowers/specs/2026-08-29-*.md). Whole-
blob fallback: if the DB row for this feature_type doesn't exist, or the
DB isn't reachable at all, the checked-in JSON file is used in full — no
per-key merging."""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.tool_config import ToolConfig


def load_tool_config(db: Session, feature_type: str, fallback_path: Path) -> dict:
    try:
        row = db.get(ToolConfig, feature_type)
        if row and row.config_json:
            return row.config_json
    except Exception:
        pass  # DB unreachable — same crash-tolerance philosophy as
              # main.py's startup tool-sync (app/tools/sync.py)
    return json.loads(fallback_path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_tool_config.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/core/tool_config.py tests/test_tool_config.py
git commit -m "feat: add load_tool_config shared DB-else-JSON loader"
```

---

## Task 4: `FalImageEditProvider`

**Files:**
- Create: `app/core/fal_provider.py`
- Test: `tests/test_fal_provider.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_fal_provider.py`:

```python
"""app/core/fal_provider.py's FalImageEditProvider — generic submit/poll
against fal's queue API. fal_client and httpx are monkeypatched throughout;
no real network call is made. SessionLocal/load_tool_config are also
monkeypatched so this doesn't need a real DB to resolve which model id to
call."""

import pytest

import app.core.fal_provider as fal_provider_module
from app.core.ai_provider import GenerationFailed, GenerationHandle, GenerationPending
from app.core.fal_provider import FalImageEditProvider


class _DummySession:
    def close(self):
        pass


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    monkeypatch.setattr(fal_provider_module, "SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(
        fal_provider_module, "load_tool_config",
        lambda db, feature_type, path: {"models": {"final_generation": "fal-ai/some/model"}},
    )


def test_submit_calls_fal_with_resolved_model_and_returns_handle(monkeypatch):
    captured = {}

    class _FakeHandle:
        request_id = "req-123"

    def fake_submit(model, arguments):
        captured["model"] = model
        captured["arguments"] = arguments
        return _FakeHandle()

    monkeypatch.setattr(fal_provider_module.fal_client, "submit", fake_submit)

    provider = FalImageEditProvider(feature_type="on_model_shots", model_config_key="final_generation")
    handle = provider.submit(
        "on_model_shots", None,
        {"prompt": "a pose", "image_urls": ["http://x/1.jpg"], "image_size": "portrait_4_3"},
    )

    assert captured["model"] == "fal-ai/some/model"
    assert captured["arguments"]["prompt"] == "a pose"
    assert captured["arguments"]["enable_safety_checker"] is True
    assert handle == GenerationHandle(external_job_id="fal-ai/some/model::req-123", provider="fal")


def test_poll_result_pending_when_in_progress(monkeypatch):
    monkeypatch.setattr(
        fal_provider_module.fal_client, "status",
        lambda model, request_id, with_logs=False: fal_provider_module.fal_client.InProgress(logs=None),
    )
    provider = FalImageEditProvider(feature_type="on_model_shots", model_config_key="final_generation")
    handle = GenerationHandle(external_job_id="fal-ai/some/model::req-123", provider="fal")

    with pytest.raises(GenerationPending):
        provider.poll_result(handle)


def test_poll_result_pending_when_queued(monkeypatch):
    monkeypatch.setattr(
        fal_provider_module.fal_client, "status",
        lambda model, request_id, with_logs=False: fal_provider_module.fal_client.Queued(position=2),
    )
    provider = FalImageEditProvider(feature_type="on_model_shots", model_config_key="final_generation")
    handle = GenerationHandle(external_job_id="fal-ai/some/model::req-123", provider="fal")

    with pytest.raises(GenerationPending):
        provider.poll_result(handle)


def test_poll_result_failed_when_fal_reports_error(monkeypatch):
    monkeypatch.setattr(
        fal_provider_module.fal_client, "status",
        lambda model, request_id, with_logs=False: fal_provider_module.fal_client.Completed(
            logs=None, metrics={}, error="nsfw content detected", error_type="content_policy",
        ),
    )
    provider = FalImageEditProvider(feature_type="on_model_shots", model_config_key="final_generation")
    handle = GenerationHandle(external_job_id="fal-ai/some/model::req-123", provider="fal")

    with pytest.raises(GenerationFailed, match="nsfw content detected"):
        provider.poll_result(handle)


def test_poll_result_downloads_bytes_when_completed(monkeypatch):
    monkeypatch.setattr(
        fal_provider_module.fal_client, "status",
        lambda model, request_id, with_logs=False: fal_provider_module.fal_client.Completed(
            logs=None, metrics={}, error=None,
        ),
    )
    monkeypatch.setattr(
        fal_provider_module.fal_client, "result",
        lambda model, request_id: {"images": [{"url": "https://fal.example/out.png"}]},
    )

    class _FakeResponse:
        content = b"fake-png-bytes"
        headers = {"content-type": "image/png"}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(fal_provider_module.httpx, "get", lambda url, timeout=60.0: _FakeResponse())

    provider = FalImageEditProvider(feature_type="on_model_shots", model_config_key="final_generation")
    handle = GenerationHandle(external_job_id="fal-ai/some/model::req-123", provider="fal")
    result = provider.poll_result(handle)

    assert result.media_type == "image"
    assert result.content == b"fake-png-bytes"
    assert result.extension == "png"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_fal_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.fal_provider'`

- [ ] **Step 3: Implement**

`app/core/fal_provider.py`:

```python
"""FalImageEditProvider — generic async submit/poll AIProvider (see
app/core/ai_provider.py) against fal.ai's queue API, for any tool that
edits/generates ONE image from a prompt + a list of input image URLs.
Knows nothing about poses, shots, prompts, or safety — those live in each
tool's own file (app/tools/on_model_shots.py, app/tools/catalog_photoshoot.py),
which builds input_payload and hands it to a configured instance of this
class. Two tools, two instances, each pointed at a different tool_config
row/key — see
docs/superpowers/specs/2026-08-29-catalog-photoshoot-tool-design.md.

Uses fal's real async submit()/status()/result() calls, not the blocking
.subscribe() the original flow.py/catalog_flow.py scripts use — submit()
here returns as soon as fal hands back a request id, poll_result() checks
status once per call, same non-blocking shape as MockAIProvider."""

from pathlib import Path

import fal_client
import httpx

from app.core.ai_provider import AIProvider, GenerationFailed, GenerationHandle, GenerationPending, GenerationResult
from app.core.db import SessionLocal
from app.core.tool_config import load_tool_config

_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _guess_extension(url: str, content_type: str) -> str:
    filename = url.rsplit("/", 1)[-1]
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix in ("jpg", "jpeg", "png", "webp", "gif"):
        return "jpg" if suffix == "jpeg" else suffix
    return _EXTENSION_BY_CONTENT_TYPE.get(content_type.split(";")[0].strip().lower(), "jpg")


class FalImageEditProvider(AIProvider):
    def __init__(self, feature_type: str, model_config_key: str):
        self.feature_type = feature_type
        self.model_config_key = model_config_key
        self._fallback_path = Path(__file__).resolve().parent.parent / "tools" / f"{feature_type}_config.json"

    def _model_id(self) -> str:
        db = SessionLocal()
        try:
            config = load_tool_config(db, self.feature_type, self._fallback_path)
        finally:
            db.close()
        return config["models"][self.model_config_key]

    def submit(self, feature_type, source_asset_url, input_payload):
        model = self._model_id()
        args = {
            "prompt": input_payload["prompt"],
            "image_urls": input_payload["image_urls"],
            "image_size": input_payload["image_size"],
            "num_images": 1,
            "max_images": 1,
            "enable_safety_checker": True,  # second, independent safety layer — do not disable
        }
        handle = fal_client.submit(model, arguments=args)
        return GenerationHandle(external_job_id=f"{model}::{handle.request_id}", provider="fal")

    def poll_result(self, handle: GenerationHandle) -> GenerationResult:
        model, request_id = handle.external_job_id.split("::", 1)
        current_status = fal_client.status(model, request_id, with_logs=False)

        if isinstance(current_status, fal_client.Completed):
            if current_status.error:
                raise GenerationFailed(current_status.error)
            result = fal_client.result(model, request_id)
            image = result["images"][0]
            resp = httpx.get(image["url"], timeout=60.0)
            resp.raise_for_status()
            extension = _guess_extension(image["url"], resp.headers.get("content-type", ""))
            return GenerationResult(media_type="image", content=resp.content, extension=extension)

        if isinstance(current_status, (fal_client.InProgress, fal_client.Queued)):
            raise GenerationPending()

        raise GenerationFailed(f"Unexpected fal status: {current_status!r}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_fal_provider.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/core/fal_provider.py tests/test_fal_provider.py
git commit -m "feat: add FalImageEditProvider (generic fal submit/poll)"
```

---

## Task 5: Per-user generation lock

**Files:**
- Modify: `app/core/queue.py`
- Modify: `app/controllers/generation_controller.py`
- Modify: `app/worker.py`
- Test: `tests/test_worker_lock_key.py`
- Test: `tests/test_generation_lock_plumbing.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_worker_lock_key.py`:

```python
"""app/worker.py's lock key — per-user, not per-team, so different members
of the same team can generate concurrently while one user's own second
generation still queues behind their first. See
docs/superpowers/specs/2026-08-29-on-model-shots-real-provider-design.md's
addendum."""

from app.worker import _user_lock_key


def test_user_lock_key_is_scoped_by_user_not_team():
    assert _user_lock_key("user-1") == "lock:user:user-1"
    assert _user_lock_key("user-1") != _user_lock_key("user-2")
```

`tests/test_generation_lock_plumbing.py`:

```python
"""Verifies POST /generate (via generation_controller.run_generation and
run_generation_bulk) threads the acting user's id through to
enqueue_generation_job — the plumbing the per-user lock in worker.py
depends on. Does not exercise the real Redis lock itself — no Redis
integration test infra exists in this project yet (same gap noted in
docs/BOOK.md for the rest of generation)."""

import asyncio

from app.controllers import generation_controller
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import Team, TeamMembership, new_id
from app.models.user import User
from app.schemas.generation import BulkGenerateRequest, GenerateRequest


def _make_team_and_user(db, role="owner"):
    team = Team(id=new_id(), name="Test Team")
    user = User(id=new_id(), email=f"{new_id()}@example.com")
    db.add_all([team, user])
    db.commit()
    db.add(TeamMembership(id=new_id(), team_id=team.id, user_id=user.id, role=role))
    db.commit()
    return team, user


def test_run_generation_enqueues_with_the_acting_users_id(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    monkeypatch.setattr(generation_controller, "_resolve_and_check_credits", lambda *a, **k: 1)

    captured = {}

    async def fake_enqueue(job_id, team_id, created_by):
        captured["job_id"] = job_id
        captured["team_id"] = team_id
        captured["created_by"] = created_by

    monkeypatch.setattr(generation_controller, "enqueue_generation_job", fake_enqueue)

    payload = GenerateRequest(team_id=team.id, feature_type="on_model_shots", input_payload={})
    job = asyncio.run(generation_controller.run_generation(db_session, user, payload))

    assert captured["created_by"] == user.id
    assert captured["team_id"] == team.id
    assert captured["job_id"] == job.id


def test_run_generation_bulk_enqueues_every_job_with_the_acting_users_id(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    assets = []
    for _ in range(2):
        asset = Asset(
            team_id=team.id, created_by=user.id, kind=AssetKind.upload.value,
            media_type=MediaType.image.value, storage_key=f"{team.id}/{new_id()}.png",
            url="http://x/1.png",
        )
        db_session.add(asset)
        assets.append(asset)
    db_session.commit()

    monkeypatch.setattr(generation_controller, "_resolve_and_check_credits", lambda *a, **k: 1)

    captured_created_by = []

    async def fake_enqueue(job_id, team_id, created_by):
        captured_created_by.append(created_by)

    monkeypatch.setattr(generation_controller, "enqueue_generation_job", fake_enqueue)

    payload = BulkGenerateRequest(
        team_id=team.id, feature_type="on_model_shots",
        asset_ids=[a.id for a in assets], input_payload={},
    )
    asyncio.run(generation_controller.run_generation_bulk(db_session, user, payload))

    assert captured_created_by == [user.id, user.id]
```

- [ ] **Step 2: Run to verify both fail**

Run: `pytest tests/test_worker_lock_key.py tests/test_generation_lock_plumbing.py -v`
Expected: FAIL — `ImportError: cannot import name '_user_lock_key'` and `TypeError: enqueue_generation_job() takes 2 positional arguments but 3 were given` (the fake still gets called with the old 2-arg signature, proving the current code doesn't pass `created_by` yet).

- [ ] **Step 3: Update `app/core/queue.py`**

Replace `enqueue_generation_job`:

```python
async def enqueue_generation_job(job_id: str, team_id: str, created_by: str) -> None:
    """Fire-and-forget: hands the job to arq and returns. The actual AI
    call happens later, in app/worker.py's run_generation_job, once that
    USER's lock is free (per-user, not per-team — different members of the
    same team can generate concurrently, see
    docs/superpowers/specs/2026-08-29-on-model-shots-real-provider-design.md's
    addendum) and a global worker slot is available."""
    pool = await get_queue_pool()
    await pool.enqueue_job("run_generation_job", job_id, team_id, created_by)
```

- [ ] **Step 4: Update both call sites in `app/controllers/generation_controller.py`**

In `run_generation`, change:

```python
        await enqueue_generation_job(job.id, payload.team_id)
```

to:

```python
        await enqueue_generation_job(job.id, payload.team_id, current_user.id)
```

In `run_generation_bulk`, change:

```python
            await enqueue_generation_job(job_id, payload.team_id)
```

to:

```python
            await enqueue_generation_job(job_id, payload.team_id, current_user.id)
```

- [ ] **Step 5: Update `app/worker.py`**

Change the docstring's lock-description paragraph (currently starting "Two independent limits apply to every run_generation_job:") — replace this bullet:

```
- a per-team Redis lock (SET NX EX below) — only one generation job for a
  given team runs at a time, whether it came from /generate or
  /generate/bulk. This is also the entire mechanism behind bulk's "one
  after another": there's no separate batch-processing code path, just
  this same lock.
```

with:

```
- a per-user Redis lock (SET NX EX below) — only one generation job for a
  given USER runs at a time; different users on the same team can run
  concurrently. Team credits stay shared (core/credits.py, unaffected by
  this), only the execution lock is now per-user. This is also the entire
  mechanism behind bulk's "one after another for that user": there's no
  separate batch-processing code path, just this same lock.
```

Change the `LOCK_TTL_SECONDS` comment's "the team isn't wedged forever" to "the user isn't wedged forever":

```python
LOCK_TTL_SECONDS = 600  # generous ceiling: if a worker crashes mid-job
# without releasing, the user isn't wedged forever, just until this expires.
```

Rename `_team_lock_key` to `_user_lock_key`:

```python
def _user_lock_key(user_id: str) -> str:
    return f"lock:user:{user_id}"
```

Update `run_generation_job`'s signature and lock-key call:

```python
async def run_generation_job(ctx: dict, job_id: str, team_id: str, created_by: str) -> None:
    redis: Redis = ctx["redis"]
    lock_key = _user_lock_key(created_by)
```

(the rest of `run_generation_job`'s body is unchanged — `team_id` is still passed through since `_process_job`/`_submit`/`_poll` don't need it directly, but keeping it as a parameter avoids reshaping the arq job's call signature beyond what's needed, and it documents which team this job belongs to for anyone reading a queued job's args)

- [ ] **Step 6: Run to verify both test files pass**

Run: `pytest tests/test_worker_lock_key.py tests/test_generation_lock_plumbing.py -v`
Expected: 3 passed

- [ ] **Step 7: Run the full existing suite to confirm nothing else broke**

Run: `pytest -q`
Expected: all pass (this change touches shared plumbing used by every tool — this is the check that nothing else silently relied on the old 2-arg `enqueue_generation_job` signature)

- [ ] **Step 8: Commit**

```bash
git add app/core/queue.py app/controllers/generation_controller.py app/worker.py tests/test_worker_lock_key.py tests/test_generation_lock_plumbing.py
git commit -m "fix: generation lock is per-user, not per-team"
```

---

## Task 6: `on_model_shots.py` — helpers + model source

**Files:**
- Modify: `app/tools/on_model_shots.py`
- Test: `tests/test_on_model_shots_tool.py`

- [ ] **Step 1: Write the failing tests (part 1 — model source + helpers)**

`tests/test_on_model_shots_tool.py`:

```python
"""app/tools/on_model_shots.py — pure logic + config-driven VLM calls.
_vlm_json_call itself is monkeypatched at the module boundary for every
test that exercises a function built on top of it — no real fal.ai call
is made in this test file."""

import pytest

from app.tools import on_model_shots as tool

_FAKE_CONFIG = {
    "models": {"final_generation": "m-final", "text_to_image": "m-t2i", "prompt_writer": "m-writer", "safety_check": "m-safety"},
    "prompts": {
        "model_prompt_writer": "sys-model-prompt", "description_safety": "sys-desc-safety",
        "image_nsfw": "sys-image-nsfw", "general": "sys-general", "intimate": "sys-intimate",
        "local_safety_check": "sys-local-safety",
    },
    "presets": {"preset_1": "https://cdn.example.com/preset_1.jpg"},
}


# --- description safety (keyword, no VLM) -------------------------------

def test_check_description_safety_raises_on_blocked_term():
    with pytest.raises(ValueError, match="Blocked term 'teen'"):
        tool.check_description_safety("a teen model in a studio")


def test_check_description_safety_passes_clean_text():
    assert tool.check_description_safety("a confident adult model in a studio") is True


# --- VLM-backed functions (mocked _vlm_json_call) ------------------------

def test_generate_model_prompt_via_llm_uses_configured_model_and_prompt(monkeypatch):
    captured = {}

    def fake_call(model, system, prompt, image_urls=None, max_tokens=1000):
        captured.update(model=model, system=system, prompt=prompt)
        return {"prompt": "a confident adult model"}

    monkeypatch.setattr(tool, "_vlm_json_call", fake_call)
    result = tool.generate_model_prompt_via_llm(_FAKE_CONFIG, "Female", "Young adult (25-30)", "Fair", "Slim")

    assert result == "a confident adult model"
    assert captured["model"] == "m-writer"
    assert captured["system"] == "sys-model-prompt"


def test_check_description_safety_llm_returns_pass_and_reason(monkeypatch):
    monkeypatch.setattr(tool, "_vlm_json_call", lambda *a, **k: {"pass": False, "reason": "age-ambiguous"})
    passed, reason = tool.check_description_safety_llm(_FAKE_CONFIG, "a description")
    assert passed is False
    assert reason == "age-ambiguous"


def test_check_image_nsfw_returns_clean_and_reason(monkeypatch):
    monkeypatch.setattr(tool, "_vlm_json_call", lambda *a, **k: {"clean": True, "reason": ""})
    clean, reason = tool.check_image_nsfw(_FAKE_CONFIG, "https://x/candidate.png")
    assert clean is True


def test_generate_model_candidate_stops_before_generation_on_description_safety_fail(monkeypatch):
    """The whole point of the two-layer description check running before
    text-to-image: a blocked description must never reach the paid
    generation call."""
    monkeypatch.setattr(tool, "generate_model_prompt_via_llm", lambda *a, **k: "a description")
    monkeypatch.setattr(tool, "check_description_safety_llm", lambda *a, **k: (False, "looked underage"))

    def _should_not_be_called(*a, **k):
        raise AssertionError("generate_model_via_text2image must not be called after a failed safety check")

    monkeypatch.setattr(tool, "generate_model_via_text2image", _should_not_be_called)

    with pytest.raises(ValueError, match="Blocked at prompt-level safety check"):
        tool.generate_model_candidate(_FAKE_CONFIG, "Female", "Young adult (25-30)", "Fair", "Slim")


def test_generate_model_candidate_returns_full_result_when_clean(monkeypatch):
    monkeypatch.setattr(tool, "generate_model_prompt_via_llm", lambda *a, **k: "a description")
    monkeypatch.setattr(tool, "check_description_safety_llm", lambda *a, **k: (True, ""))
    monkeypatch.setattr(tool, "generate_model_via_text2image", lambda *a, **k: "https://fal.example/candidate.png")
    monkeypatch.setattr(tool, "check_image_nsfw", lambda *a, **k: (True, ""))

    result = tool.generate_model_candidate(_FAKE_CONFIG, "Female", "Young adult (25-30)", "Fair", "Slim")

    assert result == {"url": "https://fal.example/candidate.png", "clean": True, "reason": "", "description": "a description"}


def test_resolve_model_via_upload_raises_on_nsfw(monkeypatch):
    monkeypatch.setattr(tool, "check_image_nsfw", lambda *a, **k: (False, "looked underage"))
    with pytest.raises(ValueError, match="looked underage"):
        tool.resolve_model_via_upload(_FAKE_CONFIG, "https://x/uploaded.jpg")


def test_resolve_model_via_upload_returns_url_when_clean(monkeypatch):
    monkeypatch.setattr(tool, "check_image_nsfw", lambda *a, **k: (True, ""))
    assert tool.resolve_model_via_upload(_FAKE_CONFIG, "https://x/uploaded.jpg") == "https://x/uploaded.jpg"


def test_resolve_model_via_default_looks_up_preset_from_config():
    assert tool.resolve_model_via_default(_FAKE_CONFIG, "preset_1") == "https://cdn.example.com/preset_1.jpg"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_on_model_shots_tool.py -v`
Expected: FAIL — `AttributeError: module 'app.tools.on_model_shots' has no attribute 'check_description_safety'` (the module currently is just the 20-line registration stub)

- [ ] **Step 3: Implement — replace `app/tools/on_model_shots.py`'s content up through model source**

Replace the entire file with (this step's content; Tasks 7–9 append more below `# 3. Garment...` — write the whole thing now, sections 3 onward get filled in by those tasks):

```python
"""on_model_shots — puts an uploaded product/garment shot on a model.

Real implementation (was a MockAIProvider stub) — ported from the
verified-against-real-fal.ai-calls flow.py, adapted to read every model id
and system prompt from DB-or-JSON config (app/core/tool_config.py's
load_tool_config(), this tool's own on_model_shots_config.json) instead of
hardcoding them — see
docs/superpowers/specs/2026-08-29-on-model-shots-real-provider-design.md.

Split across two synchronous pre-steps
(app/controllers/on_model_shots_controller.py: model image, then pose
prompts) and the existing async /generate pipeline (FalImageEditProvider,
registered at the bottom of this file — one ordinary job per pose) — see
that spec's "Architecture" section for why. Duplicates a few small helpers
(_vlm_json_call, to_hosted_url, etc.) rather than sharing them with
catalog_photoshoot.py — same "standalone on purpose" philosophy the
original catalog_flow.py's docstring states explicitly, so this tool keeps
working even if that one's file is ever removed.
"""

import json
from pathlib import Path

import fal_client
from sqlalchemy.orm import Session

from app.core.fal_provider import FalImageEditProvider
from app.core.tool_config import load_tool_config
from app.tools.registry import ToolSpec, register

_CONFIG_PATH = Path(__file__).parent / "on_model_shots_config.json"
_VLM_ENDPOINT = "openrouter/router/vision"  # fal slug every VLM/LLM call below goes through


def get_config(db: Session) -> dict:
    return load_tool_config(db, "on_model_shots", _CONFIG_PATH)


# =============================================================================
# 1. Shared helpers
# =============================================================================

def to_hosted_url(path_or_url: str) -> str:
    """Return a fal-hosted URL for a local file, or pass a URL through unchanged."""
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return fal_client.upload_file(path_or_url)


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text


def _extract_json_text(text: str) -> str:
    """Fence-strip, then fall back to the outermost {...}/[...] block if the
    text still isn't valid JSON on its own — reasoning-mandatory models
    like gemini-3.1-pro-preview (this tool's configured prompt_writer) can
    put a thinking trace in the same output string ahead of the actual
    JSON answer (same finding catalog_photoshoot.py's port confirmed)."""
    text = _strip_json_fence(text)
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = text.find(open_ch), text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue
    return text  # give up — let json.loads raise with the real parse error


def _vlm_json_call(model: str, system: str, prompt: str, image_urls: list[str] | None = None, max_tokens: int = 1000) -> dict:
    """One call through fal's openrouter/router/vision. `reasoning: True` is
    sent unconditionally — mandatory for this tool's configured
    prompt_writer model (gemini-3.1-pro-preview: 400s without it, confirmed
    2026-08-29), harmless for models that ignore it."""
    args = {
        "model": model,
        "system_prompt": system,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0,
        "reasoning": True,
    }
    if image_urls:
        args["image_urls"] = image_urls
    result = fal_client.subscribe(_VLM_ENDPOINT, arguments=args, with_logs=True)
    return json.loads(_extract_json_text(result["output"]))


# =============================================================================
# 2. Model Source — generate / upload / default
# =============================================================================

DESCRIPTION_BLOCKED_TERMS = ["child", "minor", "teen", "kid", "underage"]

GENDER_OPTIONS = ["Female", "Male"]
AGE_BRACKET_OPTIONS = ["Young adult (25-30)", "Adult (30s-40s)", "Mature adult (50+)"]
SKIN_TONE_OPTIONS = ["Fair", "Light", "Tan", "Deep"]
BODY_TYPE_OPTIONS = ["Slim", "Athletic", "Average", "Curvy", "Plus size"]


def generate_model_prompt_via_llm(config: dict, gender: str, age_bracket: str, skin_tone: str, body_type: str, additional_notes: str = "") -> str:
    attrs = {"gender": gender, "age_bracket": age_bracket, "skin_tone": skin_tone, "body_type": body_type}
    prompt_text = (
        "Structured attributes: " + json.dumps(attrs)
        + (f"\nAdditional notes from user: {additional_notes}" if additional_notes else "")
        + '\n\nReturn ONLY a JSON object: {"prompt": "<the single descriptive paragraph>"}.'
    )
    result = _vlm_json_call(
        model=config["models"]["prompt_writer"], system=config["prompts"]["model_prompt_writer"],
        prompt=prompt_text, image_urls=None, max_tokens=300,
    )
    return result["prompt"]


def check_description_safety(description: str) -> bool:
    text = description.lower()
    for term in DESCRIPTION_BLOCKED_TERMS:
        if term in text:
            raise ValueError(f"Blocked term '{term}' in model description — request not sent.")
    return True


def check_description_safety_llm(config: dict, description: str) -> tuple[bool, str]:
    result = _vlm_json_call(
        model=config["models"]["safety_check"], system=config["prompts"]["description_safety"],
        prompt=f"Model description: {description}", image_urls=None, max_tokens=150,
    )
    return bool(result["pass"]), result.get("reason", "")


def check_image_nsfw(config: dict, image_url: str) -> tuple[bool, str]:
    result = _vlm_json_call(
        model=config["models"]["safety_check"], system=config["prompts"]["image_nsfw"],
        prompt="Classify this image per the rules in the system prompt.",
        image_urls=[image_url], max_tokens=200,
    )
    return bool(result["clean"]), result.get("reason", "")


def generate_model_via_text2image(config: dict, description: str, image_size: str = "portrait_4_3") -> str:
    result = fal_client.subscribe(
        config["models"]["text_to_image"],
        arguments={"prompt": description, "image_size": image_size, "num_images": 1},
        with_logs=True,
    )
    return result["images"][0]["url"]


def generate_model_candidate(config: dict, gender: str, age_bracket: str, skin_tone: str, body_type: str, additional_notes: str = "") -> dict:
    """One full attempt: LLM writes the prompt -> hard-check the
    description (keyword, then LLM) -> text-to-image -> nsfw-check the
    result. The two description checks run BEFORE the paid text-to-image
    call, so an obviously bad request never reaches it."""
    description = generate_model_prompt_via_llm(config, gender, age_bracket, skin_tone, body_type, additional_notes)
    check_description_safety(description)
    passed, reason = check_description_safety_llm(config, description)
    if not passed:
        raise ValueError(f"Blocked at prompt-level safety check: {reason}")
    url = generate_model_via_text2image(config, description)
    clean, reason = check_image_nsfw(config, url)
    return {"url": url, "clean": clean, "reason": reason, "description": description}


def resolve_model_via_upload(config: dict, hosted_url: str) -> str:
    """Takes an already-hosted URL — the caller's own Asset.url (see
    on_model_shots_controller.py, which resolves an asset_id to its url
    before calling this) — and safety-checks it. Unlike flow.py's version,
    this never uploads a local path to fal: the backend's own storage
    already hosts the file, uploaded there via the normal asset-upload
    endpoint before this is ever called."""
    clean, reason = check_image_nsfw(config, hosted_url)
    if not clean:
        raise ValueError(f"Uploaded model image flagged nsfw ({reason}) — please upload a different photo.")
    return hosted_url


def resolve_model_via_default(config: dict, preset_id: str) -> str:
    """Node: Pick from Model Library — presets are pre-vetted, no nsfw check needed."""
    return to_hosted_url(config["presets"][preset_id])
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_on_model_shots_tool.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add app/tools/on_model_shots.py tests/test_on_model_shots_tool.py
git commit -m "feat: port on_model_shots helpers + model-source logic"
```

---

## Task 7: `on_model_shots.py` — garment assembly + output settings

**Files:**
- Modify: `app/tools/on_model_shots.py`
- Modify: `tests/test_on_model_shots_tool.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_on_model_shots_tool.py`:

```python
# --- assemble_inputs -----------------------------------------------------

def test_assemble_inputs_orders_and_labels_model_garment_reference():
    image_urls, labels = tool.assemble_inputs(
        "https://x/model.jpg", ["https://x/garment1.jpg", "https://x/garment2.jpg"], ["https://x/ref.jpg"],
    )
    assert image_urls == ["https://x/model.jpg", "https://x/garment1.jpg", "https://x/garment2.jpg", "https://x/ref.jpg"]
    assert "model reference" in labels[0]
    assert "exact product, preserve fidelity" in labels[1]
    assert "style/pose reference only" in labels[3]


def test_assemble_inputs_rejects_over_ten_images():
    garments = [f"https://x/g{i}.jpg" for i in range(10)]
    with pytest.raises(ValueError, match="exceeds the 10-image limit"):
        tool.assemble_inputs("https://x/model.jpg", garments)


# --- output settings -------------------------------------------------------

def test_build_image_size_standard_uses_aspect_ratio_map():
    assert tool.build_image_size("standard", "3:4") == "portrait_4_3"


def test_build_image_size_rejects_unknown_aspect_ratio():
    with pytest.raises(ValueError, match="Unknown aspect_ratio"):
        tool.build_image_size("standard", "21:9")


def test_build_image_size_auto_modes_pass_through():
    assert tool.build_image_size("auto_2K") == "auto_2K"
    assert tool.build_image_size("auto_4K") == "auto_4K"


def test_build_image_size_custom_requires_both_dimensions():
    with pytest.raises(ValueError, match="requires custom_width and custom_height"):
        tool.build_image_size("custom", custom_width=2048)


def test_validate_custom_size_accepts_in_range_per_axis():
    tool.validate_custom_size(2048, 2048)  # does not raise


def test_validate_custom_size_rejects_out_of_range():
    with pytest.raises(ValueError, match="isn't a valid size"):
        tool.validate_custom_size(100, 100)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_on_model_shots_tool.py -v`
Expected: FAIL — `AttributeError: module 'app.tools.on_model_shots' has no attribute 'assemble_inputs'`

- [ ] **Step 3: Append to `app/tools/on_model_shots.py`**

Add after the Model Source section (after `resolve_model_via_default`):

```python
# =============================================================================
# 3. Garment + reference images
# =============================================================================

def assemble_inputs(model_image: str, garment_images: list[str], reference_images: list[str] | None = None):
    """Returns (image_urls, labels) in order. Raises if the fal input-count
    ceiling (10) is exceeded."""
    reference_images = reference_images or []
    ordered = [("model", model_image)]
    ordered += [("garment", g) for g in garment_images]
    ordered += [("reference", r) for r in reference_images]

    if len(ordered) > 10:
        over_by = len(ordered) - 10
        raise ValueError(
            f"{len(ordered)} images (1 model + {len(garment_images)} garment + "
            f"{len(reference_images)} reference) exceeds the 10-image limit — "
            f"trim {over_by} reference image(s) and try again."
        )

    image_urls = [to_hosted_url(url) for _, url in ordered]
    labels = [
        f"Image {i+1} = {kind} ({'model reference' if kind == 'model' else 'exact product, preserve fidelity' if kind == 'garment' else 'style/pose reference only'})"
        for i, (kind, _) in enumerate(ordered)
    ]
    return image_urls, labels


# =============================================================================
# 4. Output settings — aspect ratio / resolution
# =============================================================================

ASPECT_RATIO_MAP = {
    "1:1": "square_hd",
    "3:4": "portrait_4_3",
    "9:16": "portrait_16_9",
    "4:3": "landscape_4_3",
    "16:9": "landscape_16_9",
}
RESOLUTION_MODES = ["standard", "auto_2K", "auto_4K", "custom"]
SEEDREAM_MIN_DIM = 1920
SEEDREAM_MAX_DIM = 4096
SEEDREAM_MIN_TOTAL_PX = 2560 * 1440   # 3,686,400
SEEDREAM_MAX_TOTAL_PX = 4096 * 4096   # 16,777,216


def validate_custom_size(width: int, height: int) -> None:
    per_axis_ok = SEEDREAM_MIN_DIM <= width <= SEEDREAM_MAX_DIM and SEEDREAM_MIN_DIM <= height <= SEEDREAM_MAX_DIM
    total_px = width * height
    total_ok = SEEDREAM_MIN_TOTAL_PX <= total_px <= SEEDREAM_MAX_TOTAL_PX
    if not (per_axis_ok or total_ok):
        raise ValueError(
            f"{width}x{height} isn't a valid size: each side must be "
            f"{SEEDREAM_MIN_DIM}-{SEEDREAM_MAX_DIM}px, or total pixels must be "
            f"{SEEDREAM_MIN_TOTAL_PX:,}-{SEEDREAM_MAX_TOTAL_PX:,} (you gave {total_px:,})."
        )


def build_image_size(resolution_mode: str = "standard", aspect_ratio: str = "3:4", custom_width: int | None = None, custom_height: int | None = None):
    if resolution_mode == "standard":
        if aspect_ratio not in ASPECT_RATIO_MAP:
            raise ValueError(f"Unknown aspect_ratio {aspect_ratio!r} — one of {list(ASPECT_RATIO_MAP)}")
        return ASPECT_RATIO_MAP[aspect_ratio]
    if resolution_mode in ("auto_2K", "auto_4K"):
        return resolution_mode
    if resolution_mode == "custom":
        if custom_width is None or custom_height is None:
            raise ValueError("resolution_mode='custom' requires custom_width and custom_height")
        validate_custom_size(custom_width, custom_height)
        return {"width": custom_width, "height": custom_height}
    raise ValueError(f"Unknown resolution_mode: {resolution_mode!r} — one of {RESOLUTION_MODES}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_on_model_shots_tool.py -v`
Expected: 18 passed

- [ ] **Step 5: Commit**

```bash
git add app/tools/on_model_shots.py tests/test_on_model_shots_tool.py
git commit -m "feat: port on_model_shots garment assembly + output settings"
```

---

## Task 8: `on_model_shots.py` — router, pose prompts, local safety check, tool registration

**Files:**
- Modify: `app/tools/on_model_shots.py`
- Modify: `tests/test_on_model_shots_tool.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_on_model_shots_tool.py`:

```python
# --- router ------------------------------------------------------------

def test_classify_garment_category_intimate_terms():
    assert tool.classify_garment_category("push-up bra") == "intimate"
    assert tool.classify_garment_category("cotton underwear") == "intimate"


def test_classify_garment_category_general_for_everything_else():
    assert tool.classify_garment_category("t-shirt") == "general"


# --- pose prompts + local safety check -----------------------------------

def test_generate_pose_prompts_via_vlm_picks_intimate_system_for_a_bra(monkeypatch):
    captured = {}

    def fake_call(model, system, prompt, image_urls=None, max_tokens=1000):
        captured.update(model=model, system=system)
        return ["p1", "p2"]

    monkeypatch.setattr(tool, "_vlm_json_call", fake_call)
    tool.generate_pose_prompts_via_vlm(_FAKE_CONFIG, ["https://x/1.jpg"], ["Image 1 = model"], "bra", num_poses=2)

    assert captured["system"] == "sys-intimate"
    assert captured["model"] == "m-writer"


def test_generate_pose_prompts_via_vlm_picks_general_system_for_a_tshirt(monkeypatch):
    captured = {}

    def fake_call(model, system, prompt, image_urls=None, max_tokens=1000):
        captured["system"] = system
        return ["p1"]

    monkeypatch.setattr(tool, "_vlm_json_call", fake_call)
    tool.generate_pose_prompts_via_vlm(_FAKE_CONFIG, ["https://x/1.jpg"], ["Image 1 = model"], "t-shirt", num_poses=1)
    assert captured["system"] == "sys-general"


def test_run_local_safety_check_short_circuits_on_blocked_keyword(monkeypatch):
    def _should_not_be_called(*a, **k):
        raise AssertionError("_vlm_json_call must not run when a keyword already failed the check")

    monkeypatch.setattr(tool, "_vlm_json_call", _should_not_be_called)
    passed, reason = tool.run_local_safety_check(_FAKE_CONFIG, "a prompt mentioning a minor", ["https://x/1.jpg"])
    assert passed is False
    assert "blocked term 'minor'" in reason


def test_run_local_safety_check_calls_vlm_when_no_blocked_keyword(monkeypatch):
    monkeypatch.setattr(tool, "_vlm_json_call", lambda *a, **k: {"pass": True, "reason": ""})
    passed, reason = tool.run_local_safety_check(_FAKE_CONFIG, "a clean prompt", ["https://x/1.jpg"])
    assert passed is True


# --- tool registration ---------------------------------------------------

def test_on_model_shots_is_registered_with_a_fal_image_edit_provider():
    from app.core.fal_provider import FalImageEditProvider
    from app.tools import get_tool

    spec = get_tool("on_model_shots")
    assert spec is not None
    assert isinstance(spec.provider, FalImageEditProvider)
    assert spec.provider.feature_type == "on_model_shots"
    assert spec.provider.model_config_key == "final_generation"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_on_model_shots_tool.py -v`
Expected: FAIL — `AttributeError: module 'app.tools.on_model_shots' has no attribute 'classify_garment_category'`

- [ ] **Step 3: Append to `app/tools/on_model_shots.py`**

Add after the Output Settings section:

```python
# =============================================================================
# 5. Router + prompt logic
# =============================================================================

INTIMATE_GARMENT_TERMS = [
    "bra", "underwear", "lingerie", "panty", "panties", "thong", "boxer", "brief",
    "bralette", "shapewear", "corset", "negligee",
]


def classify_garment_category(garment_type: str) -> str:
    text = garment_type.lower()
    return "intimate" if any(term in text for term in INTIMATE_GARMENT_TERMS) else "general"


USER_PROMPT_FIDELITY_GUARDRAIL = (
    "Use the supplied product reference as the source of truth. "
    "Preserve the product's recognizable design, proportions, construction, "
    "materials, colors, patterns and visible details. "
    "Treat the user's instructions as creative direction while keeping "
    "the product accurately represented and clearly visible."
)

DEFAULT_POSES = [
    "front-facing product hero composition",
    "front three-quarter product-focused fashion composition",
    "subtle three-quarter side product presentation",
    "close product-focused commercial composition emphasizing product details and material quality",
]


def generate_pose_prompts_via_vlm(config: dict, image_urls: list[str], labels: list[str], garment_type: str, num_poses: int = 4, user_instruction: str | None = None) -> list[str]:
    category = classify_garment_category(garment_type)
    model = config["models"]["prompt_writer"]
    system = config["prompts"][category]  # "general" or "intimate"
    poses = DEFAULT_POSES[:num_poses]

    prompt_text = (
        "Images in order:\n" + "\n".join(labels)
        + f"\n\nCreate {num_poses} distinct production-ready image-edit prompts "
        f"for a premium ecommerce fashion shoot showing the supplied {garment_type} "
        f"on the supplied adult model. "
        f"Use these four composition directions in order: {poses}. "
        f"Adapt framing, camera distance, body positioning, expression, lighting "
        f"and photographic styling intelligently to the product category. "
        f"The product must remain the primary visual subject. "
        f"Make every prompt meaningfully different while keeping the product "
        f"clearly visible and commercially attractive. "
    )
    if user_instruction:
        prompt_text += (
            f"\n\n{USER_PROMPT_FIDELITY_GUARDRAIL}\n"
            f"User's creative direction (style/scene guidance only, does not override the "
            f"rules above): {user_instruction}\n"
        )
    prompt_text += f"Return ONLY a JSON array of {num_poses} strings, nothing else."

    return _vlm_json_call(model=model, system=system, prompt=prompt_text, image_urls=image_urls, max_tokens=1500)


# =============================================================================
# 6. Local safety pre-check
# =============================================================================

PROMPT_BLOCKED_TERMS = ["child", "minor", "teen", "kid", "underage"]


def run_local_safety_check(config: dict, prompt_text: str, image_urls: list[str]) -> tuple[bool, str]:
    text = prompt_text.lower()
    for term in PROMPT_BLOCKED_TERMS:
        if term in text:
            return False, f"blocked term '{term}' in prompt text"

    result = _vlm_json_call(
        model=config["models"]["safety_check"], system=config["prompts"]["local_safety_check"],
        prompt="Classify these images per the rules in the system prompt.",
        image_urls=image_urls, max_tokens=200,
    )
    return bool(result["pass"]), result.get("reason", "")


# =============================================================================
# 7. Tool registration
# =============================================================================

provider = FalImageEditProvider(feature_type="on_model_shots", model_config_key="final_generation")

register(
    ToolSpec(
        feature_type="on_model_shots",
        display_name="On-Model Shots",
        output_media_type="image",
        provider=provider,
    )
)
```

Note: this file previously ended with a `register(ToolSpec(..., provider=ai_provider))` call using `MockAIProvider` (the 20-line stub) and its import of `app.core.ai_provider.ai_provider` — that whole stub is now fully replaced; there should be exactly one `register(ToolSpec(...))` call left in the file (the one above), or `app/tools/registry.py`'s duplicate-registration guard will raise at import time.

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_on_model_shots_tool.py -v`
Expected: 25 passed

- [ ] **Step 5: Run the full suite (this changes what `on_model_shots` resolves to app-wide)**

Run: `pytest -q`
Expected: all pass, including `tests/test_category_a_tools.py` and anything touching `known_feature_types()`

- [ ] **Step 6: Commit**

```bash
git add app/tools/on_model_shots.py tests/test_on_model_shots_tool.py
git commit -m "feat: port on_model_shots router/pose-prompts/local-safety-check; register FalImageEditProvider"
```

---

## Task 9: `on_model_shots` schemas + model-image controller endpoint

**Files:**
- Create: `app/schemas/on_model_shots.py`
- Create: `app/controllers/on_model_shots_controller.py`
- Test: `tests/test_on_model_shots_controller.py`

- [ ] **Step 1: Write the schemas**

`app/schemas/on_model_shots.py`:

```python
from typing import Literal

from pydantic import BaseModel


class ModelImageResolveRequest(BaseModel):
    mode: Literal["generate", "upload", "default"]
    # generate:
    gender: str = ""
    age_bracket: str = ""
    skin_tone: str = ""
    body_type: str = ""
    additional_notes: str = ""
    # upload: an Asset the caller already created via POST /teams/{id}/assets
    asset_id: str | None = None
    # default:
    preset_id: str | None = None


class ModelImageResolveResponse(BaseModel):
    asset_id: str | None
    url: str
    clean: bool
    reason: str | None = None
    description: str | None = None


class PromptsRequest(BaseModel):
    model_image_url: str
    garment_asset_ids: list[str]
    reference_asset_ids: list[str] = []
    garment_type: str = "bra"
    num_poses: int = 4
    user_prompt: str | None = None
    resolution_mode: str = "standard"
    aspect_ratio: str = "3:4"
    custom_width: int | None = None
    custom_height: int | None = None


class PromptsResponse(BaseModel):
    prompts: list[str]
    image_urls: list[str]
    labels: list[str]
    image_size: dict | str
```

- [ ] **Step 2: Write the failing tests for the model-image endpoint**

`tests/test_on_model_shots_controller.py`:

```python
"""on_model_shots_controller — the two pre-step endpoints' controller
logic. fal/VLM calls are monkeypatched at the app.tools.on_model_shots
module boundary (same "isolate the controller, trust the seam" philosophy
as tests/test_asset_library.py's storage/cache monkeypatching)."""

import pytest
from fastapi import HTTPException

from app.controllers import on_model_shots_controller as controller
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import Team, TeamMembership, new_id
from app.models.user import User
from app.schemas.on_model_shots import ModelImageResolveRequest
from app.tools import on_model_shots as tool

_FAKE_CONFIG = {
    "models": {"final_generation": "m", "text_to_image": "m", "prompt_writer": "m", "safety_check": "m"},
    "prompts": {
        "model_prompt_writer": "s", "description_safety": "s", "image_nsfw": "s",
        "general": "s", "intimate": "s", "local_safety_check": "s",
    },
    "presets": {"preset_1": "https://cdn.example.com/preset_1.jpg"},
}


def _make_team_and_user(db, role="owner"):
    team = Team(id=new_id(), name="Test Team")
    user = User(id=new_id(), email=f"{new_id()}@example.com")
    db.add_all([team, user])
    db.commit()
    db.add(TeamMembership(id=new_id(), team_id=team.id, user_id=user.id, role=role))
    db.commit()
    return team, user


def _make_asset(db, team, user, url="http://x/files/garment.jpg"):
    asset = Asset(
        team_id=team.id, created_by=user.id, kind=AssetKind.upload.value,
        media_type=MediaType.image.value, storage_key=f"{team.id}/{new_id()}.jpg", url=url,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    monkeypatch.setattr(tool, "get_config", lambda db: _FAKE_CONFIG)


class _FakeResponse:
    content = b"fake-bytes"
    headers = {"content-type": "image/png"}

    def raise_for_status(self):
        pass


def test_resolve_model_image_generate_saves_a_new_asset(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    monkeypatch.setattr(tool, "generate_model_candidate", lambda config, *a, **k: {
        "url": "https://fal.example/candidate.png", "clean": True, "reason": "", "description": "a model",
    })
    monkeypatch.setattr(controller.httpx, "get", lambda url, timeout=60.0: _FakeResponse())
    saved = {}
    monkeypatch.setattr(controller.storage, "save", lambda key, content: saved.update(key=key, content=content))
    monkeypatch.setattr(controller.storage, "url_for", lambda key: f"http://x/files/{key}")

    payload = ModelImageResolveRequest(mode="generate", gender="Female", age_bracket="Young adult (25-30)", skin_tone="Fair", body_type="Slim")
    result = controller.resolve_model_image(db_session, team.id, user, payload)

    assert result.clean is True
    assert result.description == "a model"
    assert result.asset_id is not None
    assert saved["content"] == b"fake-bytes"
    stored = db_session.get(Asset, result.asset_id)
    assert stored.kind == AssetKind.generated.value
    assert stored.team_id == team.id


def test_resolve_model_image_generate_saves_asset_even_when_flagged(db_session, monkeypatch):
    """Same 'always show it, let a human override an obvious false
    positive' philosophy as streamlit_app.py — a flagged candidate still
    becomes a real Asset, not silently dropped."""
    team, user = _make_team_and_user(db_session)
    monkeypatch.setattr(tool, "generate_model_candidate", lambda config, *a, **k: {
        "url": "https://fal.example/candidate.png", "clean": False, "reason": "looked underage", "description": "a model",
    })
    monkeypatch.setattr(controller.httpx, "get", lambda url, timeout=60.0: _FakeResponse())
    monkeypatch.setattr(controller.storage, "save", lambda key, content: None)
    monkeypatch.setattr(controller.storage, "url_for", lambda key: f"http://x/files/{key}")

    payload = ModelImageResolveRequest(mode="generate")
    result = controller.resolve_model_image(db_session, team.id, user, payload)

    assert result.clean is False
    assert result.reason == "looked underage"
    assert result.asset_id is not None


def test_resolve_model_image_upload_requires_asset_id(db_session):
    team, user = _make_team_and_user(db_session)
    payload = ModelImageResolveRequest(mode="upload")
    with pytest.raises(HTTPException) as exc_info:
        controller.resolve_model_image(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400


def test_resolve_model_image_upload_rejects_asset_from_another_team(db_session):
    team, user = _make_team_and_user(db_session)
    other_team, other_user = _make_team_and_user(db_session)
    other_asset = _make_asset(db_session, other_team, other_user)

    payload = ModelImageResolveRequest(mode="upload", asset_id=other_asset.id)
    with pytest.raises(HTTPException) as exc_info:
        controller.resolve_model_image(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400


def test_resolve_model_image_upload_raises_when_nsfw_flagged(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    asset = _make_asset(db_session, team, user)

    def _raise(*a, **k):
        raise ValueError("flagged")

    monkeypatch.setattr(tool, "resolve_model_via_upload", _raise)

    payload = ModelImageResolveRequest(mode="upload", asset_id=asset.id)
    with pytest.raises(HTTPException) as exc_info:
        controller.resolve_model_image(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400


def test_resolve_model_image_default_uses_preset_from_config(db_session):
    team, user = _make_team_and_user(db_session)
    payload = ModelImageResolveRequest(mode="default", preset_id="preset_1")
    result = controller.resolve_model_image(db_session, team.id, user, payload)
    assert result.asset_id is None
    assert result.url == "https://cdn.example.com/preset_1.jpg"


def test_resolve_model_image_default_rejects_unknown_preset(db_session):
    team, user = _make_team_and_user(db_session)
    payload = ModelImageResolveRequest(mode="default", preset_id="nope")
    with pytest.raises(HTTPException) as exc_info:
        controller.resolve_model_image(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400
```

- [ ] **Step 3: Run to verify it fails**

Run: `pytest tests/test_on_model_shots_controller.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.controllers.on_model_shots_controller'`

- [ ] **Step 4: Implement**

`app/controllers/on_model_shots_controller.py`:

```python
"""on_model_shots_controller — the two synchronous pre-steps ahead of the
existing /generate pipeline: resolving a model image (generate/upload/
default) and writing the N pose prompts. See
docs/superpowers/specs/2026-08-29-on-model-shots-real-provider-design.md.
"""

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import compute_permissions, get_membership
from app.core.storage import storage
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import new_id
from app.models.user import User
from app.schemas.on_model_shots import ModelImageResolveRequest, ModelImageResolveResponse
from app.tools import on_model_shots as tool

_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _guess_extension(content_type: str) -> str:
    return _EXTENSION_BY_CONTENT_TYPE.get(content_type.split(";")[0].strip().lower(), "jpg")


def _save_generated_image(team_id: str, user_id: str, url: str) -> Asset:
    """Downloads a fal-generated image's bytes and saves them through our
    own storage — fal's URL is never stored as the permanent Asset.url
    (see the spec's "only outputs stored" rule)."""
    resp = httpx.get(url, timeout=60.0)
    resp.raise_for_status()
    ext = _guess_extension(resp.headers.get("content-type", ""))
    key = f"{team_id}/generated/{new_id()}.{ext}"
    storage.save(key, resp.content)
    return Asset(
        team_id=team_id, created_by=user_id, kind=AssetKind.generated.value,
        media_type=MediaType.image.value, storage_key=key, url=storage.url_for(key),
    )


def resolve_model_image(
    db: Session, team_id: str, current_user: User, payload: ModelImageResolveRequest,
) -> ModelImageResolveResponse:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_generate:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to generate on this team")

    config = tool.get_config(db)

    if payload.mode == "generate":
        candidate = tool.generate_model_candidate(
            config, payload.gender, payload.age_bracket, payload.skin_tone, payload.body_type, payload.additional_notes,
        )
        asset = _save_generated_image(team_id, current_user.id, candidate["url"])
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return ModelImageResolveResponse(
            asset_id=asset.id, url=asset.url, clean=candidate["clean"],
            reason=candidate["reason"], description=candidate["description"],
        )

    if payload.mode == "upload":
        if not payload.asset_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_id is required for mode='upload'")
        asset = db.get(Asset, payload.asset_id)
        if not asset or asset.team_id != team_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_id does not belong to this team")
        try:
            url = tool.resolve_model_via_upload(config, asset.url)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        return ModelImageResolveResponse(asset_id=asset.id, url=url, clean=True, reason=None, description=None)

    if payload.mode == "default":
        if not payload.preset_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="preset_id is required for mode='default'")
        if payload.preset_id not in config.get("presets", {}):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown preset_id {payload.preset_id!r}")
        url = tool.resolve_model_via_default(config, payload.preset_id)
        return ModelImageResolveResponse(asset_id=None, url=url, clean=True, reason=None, description=None)

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown mode {payload.mode!r}")
```

`build_prompts` is added in Task 10, alongside its own tests — this task only implements and tests `resolve_model_image`.

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/test_on_model_shots_controller.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add app/schemas/on_model_shots.py app/controllers/on_model_shots_controller.py tests/test_on_model_shots_controller.py
git commit -m "feat: add on_model_shots model-image resolve endpoint logic"
```

---

## Task 10: `on_model_shots` prompts controller endpoint + routes + wiring

**Files:**
- Modify: `tests/test_on_model_shots_controller.py`
- Modify: `app/main.py`
- Create: `app/routes/on_model_shots_routes.py`

- [ ] **Step 1: Add the failing tests for `build_prompts`**

Append to `tests/test_on_model_shots_controller.py`:

```python
from app.schemas.on_model_shots import PromptsRequest


def test_build_prompts_rejects_asset_from_another_team(db_session):
    team, user = _make_team_and_user(db_session)
    other_team, other_user = _make_team_and_user(db_session)
    other_asset = _make_asset(db_session, other_team, other_user)

    payload = PromptsRequest(model_image_url="https://x/model.jpg", garment_asset_ids=[other_asset.id])
    with pytest.raises(HTTPException) as exc_info:
        controller.build_prompts(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400


def test_build_prompts_returns_prompts_and_resolved_image_size(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    garment = _make_asset(db_session, team, user, url="https://x/garment.jpg")
    monkeypatch.setattr(tool, "generate_pose_prompts_via_vlm", lambda *a, **k: ["p1", "p2"])
    monkeypatch.setattr(tool, "run_local_safety_check", lambda *a, **k: (True, ""))

    payload = PromptsRequest(
        model_image_url="https://x/model.jpg", garment_asset_ids=[garment.id],
        num_poses=2, resolution_mode="standard", aspect_ratio="3:4",
    )
    result = controller.build_prompts(db_session, team.id, user, payload)

    assert result.prompts == ["p1", "p2"]
    assert result.image_size == "portrait_4_3"
    assert result.image_urls[0] == "https://x/model.jpg"
    assert result.image_urls[1] == "https://x/garment.jpg"


def test_build_prompts_blocked_by_local_safety_check(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    garment = _make_asset(db_session, team, user, url="https://x/garment.jpg")
    monkeypatch.setattr(tool, "generate_pose_prompts_via_vlm", lambda *a, **k: ["p1"])
    monkeypatch.setattr(tool, "run_local_safety_check", lambda *a, **k: (False, "looked underage"))

    payload = PromptsRequest(model_image_url="https://x/model.jpg", garment_asset_ids=[garment.id], num_poses=1)
    with pytest.raises(HTTPException) as exc_info:
        controller.build_prompts(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400
    assert "looked underage" in exc_info.value.detail
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_on_model_shots_controller.py -v`
Expected: FAIL — `AttributeError: module 'app.controllers.on_model_shots_controller' has no attribute 'build_prompts'`

- [ ] **Step 3: Implement `build_prompts`**

In `app/controllers/on_model_shots_controller.py`, change the import line:

```python
from app.schemas.on_model_shots import ModelImageResolveRequest, ModelImageResolveResponse
```

to:

```python
from app.schemas.on_model_shots import (
    ModelImageResolveRequest,
    ModelImageResolveResponse,
    PromptsRequest,
    PromptsResponse,
)
```

Then append this function at the end of the file:

```python
def build_prompts(
    db: Session, team_id: str, current_user: User, payload: PromptsRequest,
) -> PromptsResponse:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_generate:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to generate on this team")

    config = tool.get_config(db)

    def _resolve_asset_urls(asset_ids: list[str]) -> list[str]:
        urls = []
        for asset_id in asset_ids:
            asset = db.get(Asset, asset_id)
            if not asset or asset.team_id != team_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"asset_id {asset_id!r} does not belong to this team")
            urls.append(asset.url)
        return urls

    garment_urls = _resolve_asset_urls(payload.garment_asset_ids)
    reference_urls = _resolve_asset_urls(payload.reference_asset_ids)

    try:
        image_urls, labels = tool.assemble_inputs(payload.model_image_url, garment_urls, reference_urls)
        prompts = tool.generate_pose_prompts_via_vlm(
            config, image_urls, labels, payload.garment_type, payload.num_poses, payload.user_prompt,
        )
        passed, reason = tool.run_local_safety_check(config, " ".join(prompts), image_urls)
        if not passed:
            raise ValueError(f"Blocked at local safety pre-check: {reason}")
        image_size = tool.build_image_size(payload.resolution_mode, payload.aspect_ratio, payload.custom_width, payload.custom_height)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return PromptsResponse(prompts=prompts, image_urls=image_urls, labels=labels, image_size=image_size)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_on_model_shots_controller.py -v`
Expected: 10 passed

- [ ] **Step 5: Write the routes**

`app/routes/on_model_shots_routes.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import on_model_shots_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.on_model_shots import (
    ModelImageResolveRequest,
    ModelImageResolveResponse,
    PromptsRequest,
    PromptsResponse,
)

router = APIRouter(tags=["on-model-shots"])


@router.post("/teams/{team_id}/on-model-shots/model-image", response_model=ModelImageResolveResponse)
def resolve_model_image(
    team_id: str,
    payload: ModelImageResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return on_model_shots_controller.resolve_model_image(db, team_id, current_user, payload)


@router.post("/teams/{team_id}/on-model-shots/prompts", response_model=PromptsResponse)
def build_prompts(
    team_id: str,
    payload: PromptsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return on_model_shots_controller.build_prompts(db, team_id, current_user, payload)
```

- [ ] **Step 6: Wire into `app/main.py`**

Add the import alongside the other route imports (alphabetical, after `nav_item_routes`, before `product_import_routes`):

```python
from app.routes.on_model_shots_routes import router as on_model_shots_router
```

Add the include, alongside the other `app.include_router(...)` calls (after `generation_router`):

```python
app.include_router(on_model_shots_router)
```

- [ ] **Step 7: Smoke-test the route is wired (app boots, route exists)**

Run: `python -c "from app.main import app; paths = [r.path for r in app.routes]; assert '/teams/{team_id}/on-model-shots/model-image' in paths; assert '/teams/{team_id}/on-model-shots/prompts' in paths; print('ok')"`
Expected: prints `ok`, no import errors

- [ ] **Step 8: Run the full suite**

Run: `pytest -q`
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add app/controllers/on_model_shots_controller.py tests/test_on_model_shots_controller.py app/routes/on_model_shots_routes.py app/main.py
git commit -m "feat: add on_model_shots prompts endpoint, wire both routes into main.py"
```

---

## Task 11: `catalog_photoshoot.py` — helpers, product images, output settings

**Files:**
- Create: `app/tools/catalog_photoshoot.py`
- Test: `tests/test_catalog_photoshoot_tool.py`

- [ ] **Step 1: Write the failing tests (part 1)**

`tests/test_catalog_photoshoot_tool.py`:

```python
"""app/tools/catalog_photoshoot.py — pure logic + config-driven VLM calls.
Same monkeypatch-at-the-module-boundary approach as
tests/test_on_model_shots_tool.py — no real fal.ai call is made here."""

import pytest

from app.tools import catalog_photoshoot as tool

_FAKE_CONFIG = {
    "models": {"catalog_generation": "m-catalog", "prompt_writer": "m-writer", "safety_check": "m-safety"},
    "prompts": {"shot_prompt_writer": "sys-shot-writer", "safety_check": "sys-safety"},
}


def test_assemble_product_images_labels_every_image_as_a_product_reference():
    image_urls, labels = tool.assemble_product_images(["https://x/1.jpg", "https://x/2.jpg"])
    assert image_urls == ["https://x/1.jpg", "https://x/2.jpg"]
    assert all("exact product, preserve fidelity" in label for label in labels)


def test_assemble_product_images_rejects_over_ten_images():
    with pytest.raises(ValueError, match="exceeds the 10-image input limit"):
        tool.assemble_product_images([f"https://x/{i}.jpg" for i in range(11)])


def test_build_image_size_standard_uses_aspect_ratio_map():
    assert tool.build_image_size("standard", "1:1") == "square_hd"


def test_build_image_size_auto_3k_is_supported_unlike_on_model_shots():
    assert tool.build_image_size("auto_3K") == "auto_3K"


def test_build_image_size_custom_does_not_validate_range():
    """Different from on_model_shots' build_image_size — fal auto-scales an
    out-of-range custom size for this endpoint rather than rejecting it."""
    assert tool.build_image_size("custom", custom_width=100, custom_height=100) == {"width": 100, "height": 100}
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_catalog_photoshoot_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tools.catalog_photoshoot'`

- [ ] **Step 3: Implement**

`app/tools/catalog_photoshoot.py` (this step writes the whole file; Task 12 appends the remaining sections below `# LLM+Vision...`):

```python
"""catalog_photoshoot — pure product photography: N reference images of one
product in, N distinct catalog shots out. No model-selection step (unlike
on_model_shots) — any person appearing in a shot is incidental to a
composition the VLM chose (e.g. a worn/lifestyle angle), not a chosen
identity. Real implementation ported from the verified-against-real-
fal.ai-calls catalog_flow.py, adapted to read its model ids and system
prompts from DB-or-JSON config (app/core/tool_config.py's
load_tool_config(), this tool's own catalog_photoshoot_config.json)
instead of hardcoding them — see
docs/superpowers/specs/2026-08-29-catalog-photoshoot-tool-design.md.

Standalone on purpose (duplicates a few small helpers with
on_model_shots.py rather than sharing them) — same philosophy the original
catalog_flow.py's docstring states explicitly, so this tool keeps working
even if on_model_shots.py is ever removed.
"""

import json
from pathlib import Path

import fal_client
from sqlalchemy.orm import Session

from app.core.fal_provider import FalImageEditProvider
from app.core.tool_config import load_tool_config
from app.tools.registry import ToolSpec, register

_CONFIG_PATH = Path(__file__).parent / "catalog_photoshoot_config.json"
_VLM_ENDPOINT = "openrouter/router/vision"


def get_config(db: Session) -> dict:
    return load_tool_config(db, "catalog_photoshoot", _CONFIG_PATH)


# =============================================================================
# Shared helpers
# =============================================================================

def to_hosted_url(path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return fal_client.upload_file(path_or_url)


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text


def _extract_json_text(text: str) -> str:
    text = _strip_json_fence(text)
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = text.find(open_ch), text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue
    return text


def _vlm_json_call(model: str, system: str, prompt: str, image_urls: list[str] | None = None, max_tokens: int = 1000) -> dict:
    """`reasoning: True` is mandatory for this tool's configured
    prompt_writer model (gemini-3.1-pro-preview 400s without it, confirmed
    2026-08-29) — sent unconditionally, non-reasoning models just ignore it."""
    args = {
        "model": model,
        "system_prompt": system,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0,
        "reasoning": True,
    }
    if image_urls:
        args["image_urls"] = image_urls
    result = fal_client.subscribe(_VLM_ENDPOINT, arguments=args, with_logs=True)
    return json.loads(_extract_json_text(result["output"]))


# =============================================================================
# Product images
# =============================================================================

def assemble_product_images(product_images: list[str]) -> tuple[list[str], list[str]]:
    if len(product_images) > 10:
        raise ValueError(
            f"{len(product_images)} product images exceeds the 10-image input limit — "
            f"trim {len(product_images) - 10} image(s) and try again."
        )
    image_urls = [to_hosted_url(p) for p in product_images]
    labels = [f"Image {i+1} = product reference (exact product, preserve fidelity)" for i in range(len(image_urls))]
    return image_urls, labels


# =============================================================================
# Output settings — aspect ratio / resolution
# =============================================================================

ASPECT_RATIO_MAP = {
    "1:1": "square_hd",
    "3:4": "portrait_4_3",
    "9:16": "portrait_16_9",
    "4:3": "landscape_4_3",
    "16:9": "landscape_16_9",
}
RESOLUTION_MODES = ["standard", "auto_2K", "auto_3K", "auto_4K", "custom"]
CATALOG_MIN_TOTAL_PX = 2560 * 1440
CATALOG_MAX_TOTAL_PX = 4096 * 4096


def build_image_size(resolution_mode: str = "standard", aspect_ratio: str = "1:1", custom_width: int | None = None, custom_height: int | None = None):
    """Different constraint shape from on_model_shots' build_image_size:
    catalog's endpoint (bytedance/seedream/v5/lite/edit) auto-scales an
    out-of-range custom size rather than rejecting it."""
    if resolution_mode == "standard":
        if aspect_ratio not in ASPECT_RATIO_MAP:
            raise ValueError(f"Unknown aspect_ratio {aspect_ratio!r} — one of {list(ASPECT_RATIO_MAP)}")
        return ASPECT_RATIO_MAP[aspect_ratio]
    if resolution_mode in ("auto_2K", "auto_3K", "auto_4K"):
        return resolution_mode
    if resolution_mode == "custom":
        if custom_width is None or custom_height is None:
            raise ValueError("resolution_mode='custom' requires custom_width and custom_height")
        return {"width": custom_width, "height": custom_height}  # fal auto-scales an
        # out-of-range size to fit rather than rejecting it — no validate-and-raise
        # step here, unlike on_model_shots' Seedream 4.5 edit
    raise ValueError(f"Unknown resolution_mode: {resolution_mode!r} — one of {RESOLUTION_MODES}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_catalog_photoshoot_tool.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/tools/catalog_photoshoot.py tests/test_catalog_photoshoot_tool.py
git commit -m "feat: port catalog_photoshoot helpers + product images + output settings"
```

---

## Task 12: `catalog_photoshoot.py` — safety check, shot prompts, tool registration

**Files:**
- Modify: `app/tools/catalog_photoshoot.py`
- Modify: `tests/test_catalog_photoshoot_tool.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_catalog_photoshoot_tool.py`:

```python
def test_run_safety_check_blocks_on_prompt_keyword_before_calling_vlm(monkeypatch):
    def _should_not_be_called(*a, **k):
        raise AssertionError("_vlm_json_call must not run when the prompt keyword check already failed")

    monkeypatch.setattr(tool, "_vlm_json_call", _should_not_be_called)
    passed, reason = tool.run_safety_check(_FAKE_CONFIG, ["https://x/1.jpg"], user_prompt="a photo of a minor")
    assert passed is False
    assert "blocked term 'minor'" in reason


def test_run_safety_check_calls_vlm_when_prompt_is_clean(monkeypatch):
    captured = {}

    def fake_call(model, system, prompt, image_urls=None, max_tokens=1000):
        captured.update(model=model, system=system)
        return {"pass": True, "reason": ""}

    monkeypatch.setattr(tool, "_vlm_json_call", fake_call)
    passed, _ = tool.run_safety_check(_FAKE_CONFIG, ["https://x/1.jpg"], user_prompt="a nice shot")
    assert passed is True
    assert captured["model"] == "m-safety"
    assert captured["system"] == "sys-safety"


def test_build_shot_prompts_returns_prompts_when_valid(monkeypatch):
    monkeypatch.setattr(tool, "_vlm_json_call", lambda *a, **k: ["shot1", "shot2"])
    prompts = tool.build_shot_prompts(_FAKE_CONFIG, ["https://x/1.jpg"], ["Image 1 = product"], 2)
    assert prompts == ["shot1", "shot2"]


def test_build_shot_prompts_retries_once_on_wrong_count_then_succeeds(monkeypatch):
    responses = iter([["only-one"], ["shot1", "shot2"]])
    monkeypatch.setattr(tool, "_vlm_json_call", lambda *a, **k: next(responses))
    prompts = tool.build_shot_prompts(_FAKE_CONFIG, ["https://x/1.jpg"], ["Image 1 = product"], 2)
    assert prompts == ["shot1", "shot2"]


def test_build_shot_prompts_raises_after_two_failures(monkeypatch):
    monkeypatch.setattr(tool, "_vlm_json_call", lambda *a, **k: ["shot1", "shot1"])  # duplicate, both attempts
    with pytest.raises(ValueError, match="Shot-list planning failed twice"):
        tool.build_shot_prompts(_FAKE_CONFIG, ["https://x/1.jpg"], ["Image 1 = product"], 2)


def test_catalog_photoshoot_is_registered_with_a_fal_image_edit_provider():
    from app.core.fal_provider import FalImageEditProvider
    from app.tools import get_tool

    spec = get_tool("catalog_photoshoot")
    assert spec is not None
    assert isinstance(spec.provider, FalImageEditProvider)
    assert spec.provider.feature_type == "catalog_photoshoot"
    assert spec.provider.model_config_key == "catalog_generation"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_catalog_photoshoot_tool.py -v`
Expected: FAIL — `AttributeError: module 'app.tools.catalog_photoshoot' has no attribute 'run_safety_check'`

- [ ] **Step 3: Append to `app/tools/catalog_photoshoot.py`**

```python
# =============================================================================
# Safety check
# =============================================================================

BLOCKED_TERMS = ["child", "minor", "teen", "kid", "underage"]


def run_safety_check(config: dict, image_urls: list[str], user_prompt: str | None = None) -> tuple[bool, str]:
    if user_prompt:
        text = user_prompt.lower()
        for term in BLOCKED_TERMS:
            if term in text:
                return False, f"blocked term '{term}' in prompt"

    result = _vlm_json_call(
        model=config["models"]["safety_check"], system=config["prompts"]["safety_check"],
        prompt="Classify these images per the rules in the system prompt.",
        image_urls=image_urls, max_tokens=200,
    )
    return bool(result["pass"]), result.get("reason", "")


# =============================================================================
# LLM+Vision — build N shot prompts
# =============================================================================

def _validate_shot_prompts(prompts, num_outputs: int) -> tuple[bool, str]:
    if not isinstance(prompts, list):
        return False, f"expected a JSON array, got {type(prompts).__name__}"
    if len(prompts) != num_outputs:
        return False, f"expected exactly {num_outputs} prompts, got {len(prompts)}"
    if not all(isinstance(p, str) and p.strip() for p in prompts):
        return False, "one or more prompts is empty or not a string"
    if len(set(p.strip() for p in prompts)) != len(prompts):
        return False, "duplicate prompts — the VLM repeated one shot instead of planning N distinct ones"
    return True, ""


def build_shot_prompts(config: dict, image_urls: list[str], labels: list[str], num_outputs: int, user_prompt: str | None = None) -> list[str]:
    prompt_text = (
        "Product reference images, in order:\n" + "\n".join(labels)
        + f"\n\nWrite exactly {num_outputs} distinct catalog-shot prompts for this product."
    )
    if user_prompt:
        prompt_text += (
            f"\n\nUser's additional instructions (creative direction — still preserve exact "
            f"product fidelity and the adult-only rule above): {user_prompt}"
        )
    prompt_text += f" Return ONLY a JSON array of {num_outputs} strings, nothing else."

    last_error = None
    for attempt in range(2):  # one retry
        prompts = _vlm_json_call(
            model=config["models"]["prompt_writer"], system=config["prompts"]["shot_prompt_writer"],
            prompt=prompt_text, image_urls=image_urls, max_tokens=1500,
        )
        ok, reason = _validate_shot_prompts(prompts, num_outputs)
        if ok:
            return prompts
        last_error = reason

    raise ValueError(f"Shot-list planning failed twice: {last_error}")


# =============================================================================
# Tool registration
# =============================================================================

provider = FalImageEditProvider(feature_type="catalog_photoshoot", model_config_key="catalog_generation")

register(
    ToolSpec(
        feature_type="catalog_photoshoot",
        display_name="Catalog Photoshoot",
        output_media_type="image",
        provider=provider,
    )
)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_catalog_photoshoot_tool.py -v`
Expected: 11 passed

- [ ] **Step 5: Run the full suite (a brand-new feature_type now exists app-wide)**

Run: `pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add app/tools/catalog_photoshoot.py tests/test_catalog_photoshoot_tool.py
git commit -m "feat: port catalog_photoshoot safety check + shot prompts; register tool"
```

---

## Task 13: `catalog_photoshoot` schema + controller + routes + wiring

**Files:**
- Create: `app/schemas/catalog_photoshoot.py`
- Create: `app/controllers/catalog_photoshoot_controller.py`
- Create: `app/routes/catalog_photoshoot_routes.py`
- Modify: `app/main.py`
- Test: `tests/test_catalog_photoshoot_controller.py`

- [ ] **Step 1: Write the schema**

`app/schemas/catalog_photoshoot.py`:

```python
from pydantic import BaseModel


class CatalogShotsRequest(BaseModel):
    product_asset_ids: list[str]
    num_outputs: int = 6
    resolution_mode: str = "standard"
    aspect_ratio: str = "1:1"
    custom_width: int | None = None
    custom_height: int | None = None
    user_prompt: str | None = None


class CatalogShotsResponse(BaseModel):
    prompts: list[str]
    image_urls: list[str]
    labels: list[str]
    image_size: dict | str
```

- [ ] **Step 2: Write the failing tests**

`tests/test_catalog_photoshoot_controller.py`:

```python
"""catalog_photoshoot_controller — the one pre-step endpoint's controller
logic. fal/VLM calls are monkeypatched at the app.tools.catalog_photoshoot
module boundary."""

import pytest
from fastapi import HTTPException

from app.controllers import catalog_photoshoot_controller as controller
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import Team, TeamMembership, new_id
from app.models.user import User
from app.schemas.catalog_photoshoot import CatalogShotsRequest
from app.tools import catalog_photoshoot as tool

_FAKE_CONFIG = {
    "models": {"catalog_generation": "m", "prompt_writer": "m", "safety_check": "m"},
    "prompts": {"shot_prompt_writer": "s", "safety_check": "s"},
}


def _make_team_and_user(db, role="owner"):
    team = Team(id=new_id(), name="Test Team")
    user = User(id=new_id(), email=f"{new_id()}@example.com")
    db.add_all([team, user])
    db.commit()
    db.add(TeamMembership(id=new_id(), team_id=team.id, user_id=user.id, role=role))
    db.commit()
    return team, user


def _make_asset(db, team, user, url="https://x/product.jpg"):
    asset = Asset(
        team_id=team.id, created_by=user.id, kind=AssetKind.upload.value,
        media_type=MediaType.image.value, storage_key=f"{team.id}/{new_id()}.jpg", url=url,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    monkeypatch.setattr(tool, "get_config", lambda db: _FAKE_CONFIG)


def test_build_shots_rejects_asset_from_another_team(db_session):
    team, user = _make_team_and_user(db_session)
    other_team, other_user = _make_team_and_user(db_session)
    other_asset = _make_asset(db_session, other_team, other_user)

    payload = CatalogShotsRequest(product_asset_ids=[other_asset.id])
    with pytest.raises(HTTPException) as exc_info:
        controller.build_shots(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400


def test_build_shots_blocked_by_safety_check(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    product = _make_asset(db_session, team, user)
    monkeypatch.setattr(tool, "run_safety_check", lambda *a, **k: (False, "explicit content"))

    payload = CatalogShotsRequest(product_asset_ids=[product.id])
    with pytest.raises(HTTPException) as exc_info:
        controller.build_shots(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400
    assert "explicit content" in exc_info.value.detail


def test_build_shots_returns_prompts_and_resolved_image_size(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    product = _make_asset(db_session, team, user, url="https://x/shoe.jpg")
    monkeypatch.setattr(tool, "run_safety_check", lambda *a, **k: (True, ""))
    monkeypatch.setattr(tool, "build_shot_prompts", lambda *a, **k: ["shot1", "shot2"])

    payload = CatalogShotsRequest(product_asset_ids=[product.id], num_outputs=2, aspect_ratio="1:1")
    result = controller.build_shots(db_session, team.id, user, payload)

    assert result.prompts == ["shot1", "shot2"]
    assert result.image_urls == ["https://x/shoe.jpg"]
    assert result.image_size == "square_hd"
```

- [ ] **Step 3: Run to verify it fails**

Run: `pytest tests/test_catalog_photoshoot_controller.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.controllers.catalog_photoshoot_controller'`

- [ ] **Step 4: Implement the controller**

`app/controllers/catalog_photoshoot_controller.py`:

```python
"""catalog_photoshoot_controller — the one pre-step endpoint ahead of the
existing /generate pipeline: assembling product images, running the
safety check, and writing the N shot prompts. See
docs/superpowers/specs/2026-08-29-catalog-photoshoot-tool-design.md.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import compute_permissions, get_membership
from app.models.asset import Asset
from app.models.user import User
from app.schemas.catalog_photoshoot import CatalogShotsRequest, CatalogShotsResponse
from app.tools import catalog_photoshoot as tool


def build_shots(
    db: Session, team_id: str, current_user: User, payload: CatalogShotsRequest,
) -> CatalogShotsResponse:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_generate:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to generate on this team")

    config = tool.get_config(db)

    product_urls = []
    for asset_id in payload.product_asset_ids:
        asset = db.get(Asset, asset_id)
        if not asset or asset.team_id != team_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"asset_id {asset_id!r} does not belong to this team")
        product_urls.append(asset.url)

    try:
        image_urls, labels = tool.assemble_product_images(product_urls)
        passed, reason = tool.run_safety_check(config, image_urls, payload.user_prompt)
        if not passed:
            raise ValueError(f"Blocked at safety check: {reason}")
        prompts = tool.build_shot_prompts(config, image_urls, labels, payload.num_outputs, payload.user_prompt)
        image_size = tool.build_image_size(payload.resolution_mode, payload.aspect_ratio, payload.custom_width, payload.custom_height)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return CatalogShotsResponse(prompts=prompts, image_urls=image_urls, labels=labels, image_size=image_size)
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/test_catalog_photoshoot_controller.py -v`
Expected: 3 passed

- [ ] **Step 6: Write the routes**

`app/routes/catalog_photoshoot_routes.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import catalog_photoshoot_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.catalog_photoshoot import CatalogShotsRequest, CatalogShotsResponse

router = APIRouter(tags=["catalog-photoshoot"])


@router.post("/teams/{team_id}/catalog-photoshoot/shots", response_model=CatalogShotsResponse)
def build_shots(
    team_id: str,
    payload: CatalogShotsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return catalog_photoshoot_controller.build_shots(db, team_id, current_user, payload)
```

- [ ] **Step 7: Wire into `app/main.py`**

Add the import alongside the other route imports (alphabetical, right before `generation_routes`):

```python
from app.routes.catalog_photoshoot_routes import router as catalog_photoshoot_router
```

Add the include, alongside the other `app.include_router(...)` calls (right before `generation_router`, or anywhere in that block):

```python
app.include_router(catalog_photoshoot_router)
```

- [ ] **Step 8: Smoke-test the route is wired**

Run: `python -c "from app.main import app; paths = [r.path for r in app.routes]; assert '/teams/{team_id}/catalog-photoshoot/shots' in paths; print('ok')"`
Expected: prints `ok`

- [ ] **Step 9: Run the full suite**

Run: `pytest -q`
Expected: all pass

- [ ] **Step 10: Commit**

```bash
git add app/schemas/catalog_photoshoot.py app/controllers/catalog_photoshoot_controller.py app/routes/catalog_photoshoot_routes.py app/main.py tests/test_catalog_photoshoot_controller.py
git commit -m "feat: add catalog_photoshoot shots endpoint, wire route into main.py"
```

---

## Task 14: Final full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite one more time**

Run: `pytest -q`
Expected: all pass, no warnings about duplicate `feature_type` registration, no import errors

- [ ] **Step 2: Confirm both new tools show up in the registry**

Run: `python -c "from app.tools import known_feature_types; print(known_feature_types())"`
Expected: output includes both `'catalog_photoshoot'` and `'on_model_shots'`

- [ ] **Step 3: Confirm the alembic migration applies cleanly (schema check only — does not require a real DB connection beyond what `alembic upgrade head` needs)**

Run: `alembic upgrade head` (against whatever `DATABASE_URL` is configured for local dev)
Expected: runs without error; `tool_config` table now exists

- [ ] **Step 4: No commit needed — this task is verification only**

---

## Known gaps carried over from the specs (not addressed by this plan)

- Local storage URLs must be publicly reachable for fal.ai to fetch them as `image_urls` — fine behind a real `BACKEND_URL` in production, broken on `localhost`. Same gap `docs/BOOK.md` already lists for cloud storage generally.
- No credit charge on either tool's pre-step endpoints (model-image resolve, prompts, shots) — only the per-pose/per-shot `/generate` job costs credits, via the existing unmodified mechanism.
- No automated Redis-lock integration test — `tests/test_generation_lock_plumbing.py` and `tests/test_worker_lock_key.py` cover the plumbing and the key format, not real Redis contention behavior, matching this project's existing lack of Redis test infra.
