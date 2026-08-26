# B5 — Export / Resize Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /assets/{asset_id}/export` — resize/reformat an asset into named marketplace presets (Shopify/Amazon/Etsy/Instagram/master PNG), each becoming its own new `Asset` (`kind="exported"`) linked back via `source_asset_id`.

**Architecture:** A genuinely new concern, not a table+routes exercise — needs an actual image-processing step. New `core/image_ops.py` (Pillow) does the resize/reformat; runs **synchronously in the request** (a Pillow resize is milliseconds, so this skips inventing a job/poll shape for something that doesn't need one). Needs a new `Storage.read()` method (nothing reads a file back today — every existing caller only ever writes and serves via the mounted static directory), a new `Asset.source_asset_id` self-referential column, a new `AssetKind.exported`, and a new `CreditReason.export_spend`. Charges 1 credit per preset (confirmed with you).

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, Pillow, pytest.

---

### Task 1: `Storage.read()`

**Files:**
- Modify: `app/core/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_storage.py`:

```python
def test_read_returns_saved_bytes(tmp_path):
    storage = LocalStorage(root_dir=str(tmp_path), base_url="http://x/files")
    storage.save("team-1/thing.png", b"hello world")

    assert storage.read("team-1/thing.png") == b"hello world"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/Scripts/python.exe -m pytest tests/test_storage.py -v -k test_read_returns_saved_bytes`
Expected: FAIL — `AttributeError: 'LocalStorage' object has no attribute 'read'`

- [ ] **Step 3: Implement `read()`**

In `app/core/storage.py`, add to the `Storage` ABC (after `delete`):

```python
    @abstractmethod
    def read(self, key: str) -> bytes: ...
```

And to `LocalStorage` (after its `delete`):

```python
    def read(self, key: str) -> bytes:
        return (self.root_dir / key).read_bytes()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/Scripts/python.exe -m pytest tests/test_storage.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/core/storage.py tests/test_storage.py
git commit -m "feat(storage): add Storage.read()

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `core/image_ops.py`

**Files:**
- Modify: `requirements.txt`
- Create: `app/core/image_ops.py`
- Test: `tests/test_image_ops.py`

- [ ] **Step 1: Install and pin Pillow**

Run: `./venv/Scripts/python.exe -m pip install Pillow`
Then run: `./venv/Scripts/python.exe -m pip show Pillow` to get the installed
version, and append a matching line to `requirements.txt`, e.g. `Pillow==11.0.0`
(use whatever version was actually installed).

- [ ] **Step 2: Write the failing tests**

```python
"""tests/test_image_ops.py — export_variant()'s resize/reformat/pad logic."""

import io

import pytest
from PIL import Image

from app.core.image_ops import EXPORT_PRESETS, export_variant


def _png_bytes(width, height, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def test_shopify_product_produces_exact_square_jpeg():
    result_bytes, ext = export_variant(_png_bytes(800, 400), "shopify_product")

    assert ext == "jpg"
    image = Image.open(io.BytesIO(result_bytes))
    assert image.size == (2048, 2048)
    assert image.format == "JPEG"


def test_amazon_main_pads_a_non_square_source_with_white():
    result_bytes, _ext = export_variant(_png_bytes(1000, 400), "amazon_main")

    image = Image.open(io.BytesIO(result_bytes)).convert("RGB")
    assert image.size == (3000, 3000)
    # A wide source contained within a 3000x3000 square leaves the top
    # strip as padding — must be white, not the source's red fill.
    assert image.getpixel((0, 0)) == (255, 255, 255)


def test_master_png_caps_max_dimension_without_upscaling_a_smaller_source():
    result_bytes, ext = export_variant(_png_bytes(500, 300), "master_png")

    assert ext == "png"
    image = Image.open(io.BytesIO(result_bytes))
    assert image.size == (500, 300)  # untouched — already smaller than the cap


def test_master_png_downscales_a_larger_source_to_the_cap():
    result_bytes, _ext = export_variant(_png_bytes(5000, 2500), "master_png")

    image = Image.open(io.BytesIO(result_bytes))
    assert image.size == (4096, 2048)  # aspect preserved, capped at 4096


def test_export_variant_rejects_an_unknown_preset():
    with pytest.raises(ValueError):
        export_variant(_png_bytes(100, 100), "not_a_real_preset")


def test_all_five_presets_are_defined():
    assert set(EXPORT_PRESETS.keys()) == {
        "shopify_product", "amazon_main", "etsy_listing", "instagram_post", "master_png",
    }
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `./venv/Scripts/python.exe -m pytest tests/test_image_ops.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.image_ops'`

- [ ] **Step 4: Implement `app/core/image_ops.py`**

```python
"""Resize + reformat an asset into a named marketplace preset. A genuinely
separate concern from the AI generation pipeline (core/ai_provider.py) —
this never touches AIProvider. Amazon's white-background requirement is a
plain letterbox/pad, not real background removal — that's background_swap
(a Category-A tool), not this module's job.
"""

from io import BytesIO

from PIL import Image, ImageOps

# (target_width, target_height, output_format, mode)
#   mode "fit"     — crop-to-fill: exact target dimensions, cropping any excess
#   mode "pad"     — contain within target, pad remaining space with white
#   mode "contain" — preserve aspect, cap the max dimension, never upscale
EXPORT_PRESETS = {
    "shopify_product": (2048, 2048, "JPEG", "fit"),
    "amazon_main": (3000, 3000, "JPEG", "pad"),
    "etsy_listing": (2700, 2025, "JPEG", "fit"),
    "instagram_post": (1080, 1350, "JPEG", "fit"),
    "master_png": (4096, 4096, "PNG", "contain"),
}

_EXTENSION_FOR_FORMAT = {"JPEG": "jpg", "PNG": "png"}


def export_variant(source_bytes: bytes, preset_key: str) -> tuple[bytes, str]:
    if preset_key not in EXPORT_PRESETS:
        raise ValueError(f"unknown export preset {preset_key!r} — known: {', '.join(EXPORT_PRESETS)}")

    target_w, target_h, output_format, mode = EXPORT_PRESETS[preset_key]
    image = ImageOps.exif_transpose(Image.open(BytesIO(source_bytes)))
    if output_format == "JPEG":
        image = image.convert("RGB")  # JPEG has no alpha channel

    if mode == "fit":
        result = ImageOps.fit(image, (target_w, target_h), Image.LANCZOS)
    elif mode == "pad":
        fitted = ImageOps.contain(image, (target_w, target_h), Image.LANCZOS)
        result = Image.new("RGB", (target_w, target_h), "white")
        offset = ((target_w - fitted.width) // 2, (target_h - fitted.height) // 2)
        result.paste(fitted, offset)
    else:  # "contain" — preserve aspect, no crop, no pad, never upscale
        result = image.copy()
        result.thumbnail((target_w, target_h), Image.LANCZOS)

    buffer = BytesIO()
    result.save(buffer, format=output_format)
    return buffer.getvalue(), _EXTENSION_FOR_FORMAT[output_format]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./venv/Scripts/python.exe -m pytest tests/test_image_ops.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Run the full suite**

Run: `./venv/Scripts/python.exe -m pytest`
Expected: all passing

- [ ] **Step 7: Commit**

```bash
git add requirements.txt app/core/image_ops.py tests/test_image_ops.py
git commit -m "feat(export): add core/image_ops.py (Pillow resize/reformat presets)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `Asset.source_asset_id`, `AssetKind.exported`, `CreditReason.export_spend`

**Files:**
- Modify: `app/models/asset.py`
- Modify: `app/models/credit.py`
- Create: migration (via autogenerate)

- [ ] **Step 1: Add `exported` to `AssetKind` in `app/models/asset.py`**

```python
class AssetKind(str, enum.Enum):
    upload = "upload"
    generated = "generated"
    imported = "imported"
    exported = "exported"  # produced by POST /assets/{id}/export (B5) — a
    # Pillow-resized/reformatted derivative of another asset, not an AI
    # generation output. source_asset_id (below) says which asset it's from.
```

- [ ] **Step 2: Add `source_asset_id` to the `Asset` model**

Insert right after `is_saved_product = Column(...)`:

```python
    source_asset_id = Column(String, ForeignKey("assets.id"), nullable=True)  # set
    # only for kind="exported" — which asset this resize/reformat
    # derivative came from (B5). Self-referential FK, same one-hop-lineage
    # pointer pattern as GenerationJob.source_asset_id/output_asset_id.
```

- [ ] **Step 3: Add `export_spend` to `CreditReason` in `app/models/credit.py`**

```python
    export_spend = "export_spend"  # POST /assets/{id}/export — 1 credit
    # per requested preset, charged once for the whole call. Pure
    # image-processing, no AI provider involved, kept as its own reason so
    # it's distinguishable from generation_spend in the ledger/activity feed.
```

- [ ] **Step 4: Autogenerate and apply the migration**

Run: `./venv/Scripts/python.exe -m alembic revision --autogenerate -m "add asset source_asset_id for exports"`
Open the generated file and confirm it only adds `assets.source_asset_id`
(a nullable column needs no `server_default`, unlike Task 2's earlier
`is_saved_product`).
Run: `./venv/Scripts/python.exe -m alembic upgrade head`

- [ ] **Step 5: Run the full suite**

Run: `./venv/Scripts/python.exe -m pytest`
Expected: all passing

- [ ] **Step 6: Commit**

```bash
git add app/models/asset.py app/models/credit.py alembic/versions/
git commit -m "feat(export): add Asset.source_asset_id, AssetKind.exported, CreditReason.export_spend

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: `schemas/exports.py`

**Files:**
- Create: `app/schemas/exports.py`

- [ ] **Step 1: Create the schema file**

```python
from pydantic import BaseModel, Field


class ExportRequest(BaseModel):
    presets: list[str] = Field(min_length=1, max_length=5)


class ExportResultItem(BaseModel):
    preset: str
    asset_id: str
    url: str


class ExportResponse(BaseModel):
    exports: list[ExportResultItem]
```

- [ ] **Step 2: Commit**

```bash
git add app/schemas/exports.py
git commit -m "feat(export): add export request/response schemas

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: `asset_controller.export_asset`

**Files:**
- Modify: `app/controllers/asset_controller.py`
- Test: `tests/test_export.py`

- [ ] **Step 1: Write the failing tests**

```python
"""tests/test_export.py — export_asset's credit-check, preset-validation,
and asset-creation logic. Storage is monkeypatched; image_ops runs for
real (fast, in-memory, no reason to mock Pillow itself)."""

import io

import pytest
from fastapi import HTTPException
from PIL import Image

from app.controllers import asset_controller
from app.models.asset import Asset, AssetKind
from app.models.credit import CreditReason, CreditTransaction, TeamCreditBalance
from app.models.team import Team, TeamMembership, new_id
from app.models.user import User


def _make_team_and_user(db, balance=10, role="owner"):
    team = Team(id=new_id(), name="Test Team")
    user = User(id=new_id(), email=f"{new_id()}@example.com")
    db.add_all([team, user])
    db.commit()
    db.add(TeamMembership(id=new_id(), team_id=team.id, user_id=user.id, role=role))
    db.add(TeamCreditBalance(team_id=team.id, balance=balance))
    db.commit()
    return team, user


def _make_source_asset(db, team, user):
    buf = io.BytesIO()
    Image.new("RGB", (800, 400), (200, 30, 30)).save(buf, format="PNG")
    asset = Asset(
        team_id=team.id, created_by=user.id, kind=AssetKind.upload.value, media_type="image",
        storage_key=f"{team.id}/source.png", url=f"http://x/files/{team.id}/source.png",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset, buf.getvalue()


def test_export_asset_creates_one_asset_per_preset_and_deducts_credits(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session, balance=10)
    source, source_bytes = _make_source_asset(db_session, team, user)
    monkeypatch.setattr(asset_controller.storage, "read", lambda key: source_bytes)
    saved = []
    monkeypatch.setattr(asset_controller.storage, "save", lambda key, content: saved.append(key))

    result = asset_controller.export_asset(db_session, source.id, user, ["shopify_product", "master_png"])

    assert len(result.exports) == 2
    assert len(saved) == 2
    exported_rows = db_session.query(Asset).filter(Asset.kind == AssetKind.exported.value).all()
    assert len(exported_rows) == 2
    assert all(r.source_asset_id == source.id for r in exported_rows)

    tx = db_session.query(CreditTransaction).filter(CreditTransaction.reason == CreditReason.export_spend.value).one()
    assert tx.amount == -2
    balance = db_session.query(TeamCreditBalance).filter(TeamCreditBalance.team_id == team.id).one()
    assert balance.balance == 8


def test_export_asset_402s_when_insufficient_credits(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session, balance=1)
    source, source_bytes = _make_source_asset(db_session, team, user)
    monkeypatch.setattr(asset_controller.storage, "read", lambda key: source_bytes)
    monkeypatch.setattr(asset_controller.storage, "save", lambda key, content: None)

    with pytest.raises(HTTPException) as exc_info:
        asset_controller.export_asset(db_session, source.id, user, ["shopify_product", "master_png"])
    assert exc_info.value.status_code == 402


def test_export_asset_400s_for_an_unknown_preset(db_session):
    team, user = _make_team_and_user(db_session)
    source, _bytes = _make_source_asset(db_session, team, user)

    with pytest.raises(HTTPException) as exc_info:
        asset_controller.export_asset(db_session, source.id, user, ["not_a_real_preset"])
    assert exc_info.value.status_code == 400


def test_export_asset_404s_for_a_missing_source_asset(db_session):
    _team, user = _make_team_and_user(db_session)

    with pytest.raises(HTTPException) as exc_info:
        asset_controller.export_asset(db_session, "does-not-exist", user, ["shopify_product"])
    assert exc_info.value.status_code == 404


def test_export_asset_404s_for_a_non_member(db_session):
    team, owner = _make_team_and_user(db_session)
    _, outsider = _make_team_and_user(db_session)
    source, _bytes = _make_source_asset(db_session, team, owner)

    with pytest.raises(HTTPException) as exc_info:
        asset_controller.export_asset(db_session, source.id, outsider, ["shopify_product"])
    assert exc_info.value.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/Scripts/python.exe -m pytest tests/test_export.py -v`
Expected: FAIL — `AttributeError: module 'app.controllers.asset_controller' has no attribute 'export_asset'`

- [ ] **Step 3: Implement `export_asset` in `app/controllers/asset_controller.py`**

Add these imports at the top (alongside the existing ones):

```python
from app.core.credits import apply_credit_delta, get_balance
from app.core.image_ops import EXPORT_PRESETS, export_variant
from app.models.credit import CreditReason
from app.schemas.exports import ExportResponse, ExportResultItem
```

Then append:

```python
def export_asset(db: Session, asset_id: str, current_user: User, presets: list[str]) -> ExportResponse:
    source = db.get(Asset, asset_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    membership = get_membership(db, source.team_id, current_user.id)
    if not compute_permissions(membership.role).can_upload_assets:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to export assets on this team")

    unknown = [p for p in presets if p not in EXPORT_PRESETS]
    if unknown:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown export preset(s): {', '.join(unknown)}")

    cost = len(presets)  # 1 credit per preset — no "held credits" concept
    # needed here (unlike generation_controller's), since this runs
    # synchronously, not queued: nothing can race it mid-flight.
    balance = get_balance(db, source.team_id)
    if balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits: need {cost}, have {balance}",
        )

    content = storage.read(source.storage_key)
    exports: list[ExportResultItem] = []
    for preset in presets:
        result_bytes, ext = export_variant(content, preset)
        key = f"{source.team_id}/exports/{new_id()}.{ext}"
        storage.save(key, result_bytes)
        exported_asset = Asset(
            team_id=source.team_id,
            created_by=current_user.id,
            kind=AssetKind.exported.value,
            media_type=MediaType.image.value,
            storage_key=key,
            url=storage.url_for(key),
            source_asset_id=source.id,
        )
        db.add(exported_asset)
        db.commit()
        db.refresh(exported_asset)
        exports.append(ExportResultItem(preset=preset, asset_id=exported_asset.id, url=exported_asset.url))

    apply_credit_delta(db, source.team_id, amount=-cost, reason=CreditReason.export_spend.value, reference_id=source.id)
    return ExportResponse(exports=exports)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/Scripts/python.exe -m pytest tests/test_export.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the full suite**

Run: `./venv/Scripts/python.exe -m pytest`
Expected: all passing

- [ ] **Step 6: Commit**

```bash
git add app/controllers/asset_controller.py tests/test_export.py
git commit -m "feat(export): add export_asset controller

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Route

**Files:**
- Modify: `app/routes/asset_routes.py`

- [ ] **Step 1: Add the import and route**

Add `ExportRequest, ExportResponse` to the imports (new line, since these
live in `app.schemas.exports`, not `app.schemas.assets`):

```python
from app.schemas.exports import ExportRequest, ExportResponse
```

Append:

```python
@router.post("/assets/{asset_id}/export", response_model=ExportResponse)
def export_asset(
    asset_id: str,
    payload: ExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return asset_controller.export_asset(db, asset_id, current_user, payload.presets)
```

- [ ] **Step 2: Run the full suite**

Run: `./venv/Scripts/python.exe -m pytest`
Expected: all passing

- [ ] **Step 3: Commit**

```bash
git add app/routes/asset_routes.py
git commit -m "feat(export): add POST /assets/{asset_id}/export route

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Manual end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Confirm the route exists**

Run: `./venv/Scripts/python.exe -m uvicorn app.main:app --port 8123` then
`curl.exe -s http://localhost:8123/openapi.json | ./venv/Scripts/python.exe -c "import json,sys; print(sorted(json.load(sys.stdin)['paths'].get('/assets/{asset_id}/export', {}).keys()))"`
Expected: `['post']`. Stop the server (Ctrl+C) after.

---

## Self-Review Notes

- **Spec coverage:** `Storage.read()`, `core/image_ops.py`'s 5 presets (Amazon's white pad explicitly not real background removal), `Asset.source_asset_id`/`AssetKind.exported`, synchronous (not queued) execution, 1 credit per preset, `CreditReason.export_spend` — all covered.
- **Placeholder scan:** none.
- **Type consistency:** `export_variant(source_bytes, preset_key) -> tuple[bytes, str]` matches its two call sites (test and controller); `export_asset(db, asset_id, current_user, presets) -> ExportResponse` matches its route call and test calls.
