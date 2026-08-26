# Category A — 10 Tool Registrations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register 10 new `feature_type`s (`product_photoshoot`, `background_swap`, `mockup_studio`, `flat_lay_angles`, `magic_erase`, `inpaint`, `relight_shadows`, `upscale_4k`, `resize_outpaint`, `product_motion`) so `/generate` and `/generate/bulk` work for them immediately via `MockAIProvider`.

**Architecture:** Each tool is a ~10-line file in `app/tools/` copying the exact pattern of `app/tools/on_model_shots.py` (`register(ToolSpec(...))`), auto-discovered by `app/tools/__init__.py`'s `pkgutil` loop — zero edits to routes, schemas, or `__init__.py`. A data-only Alembic migration pre-seeds the `tools` DB rows with correct `credit_cost` values (1 for nine tools, 4 for `product_motion`), following the exact pattern of the existing `3adad199e5b6_register_product_import_as_a_` migration, since `credit_cost` is DB-owned and `sync_tools_to_db()` only defaults it to 1 on first insert.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, pytest (see `tests/conftest.py`'s in-memory SQLite fixtures).

---

### Task 1: Write the failing registry test

**Files:**
- Create: `tests/test_category_a_tools.py`

- [ ] **Step 1: Write the failing test**

```python
"""tests/test_category_a_tools.py — verifies the 10 Category-A tools from
BACKEND-NEEDS.md are registered in the code registry (app/tools/) and get
mirrored into the tools DB table with the right output_media_type by
sync_tools_to_db(). credit_cost correctness (product_motion=4) is seeded by
an Alembic migration against real Postgres, not covered here — see
alembic/versions/ (this test's sqlite fixture runs Base.metadata.create_all,
not alembic migrations, so a migration-seeded value can't be asserted here).
"""

from app.models.tool import Tool
from app.tools import known_feature_types
from app.tools.sync import sync_tools_to_db

CATEGORY_A_FEATURE_TYPES = [
    "product_photoshoot",
    "background_swap",
    "mockup_studio",
    "flat_lay_angles",
    "magic_erase",
    "inpaint",
    "relight_shadows",
    "upscale_4k",
    "resize_outpaint",
    "product_motion",
]


def test_all_category_a_tools_registered():
    known = known_feature_types()
    missing = [ft for ft in CATEGORY_A_FEATURE_TYPES if ft not in known]
    assert not missing, f"not registered: {missing}"


def test_sync_creates_rows_with_correct_media_type(db_session):
    sync_tools_to_db(db_session)
    rows = {t.feature_type: t for t in db_session.query(Tool).all()}

    missing = [ft for ft in CATEGORY_A_FEATURE_TYPES if ft not in rows]
    assert not missing, f"missing from tools table after sync: {missing}"

    assert rows["product_motion"].output_media_type == "video"
    for feature_type in CATEGORY_A_FEATURE_TYPES:
        if feature_type != "product_motion":
            assert rows[feature_type].output_media_type == "image", feature_type
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/Scripts/python.exe -m pytest tests/test_category_a_tools.py -v`
Expected: FAIL — `assert not missing` fails listing all 10 feature types (none registered yet).

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/test_category_a_tools.py
git commit -m "test(tools): add failing test for category A tool registrations

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Create the 10 tool registration files

**Files:**
- Create: `app/tools/product_photoshoot.py`
- Create: `app/tools/background_swap.py`
- Create: `app/tools/mockup_studio.py`
- Create: `app/tools/flat_lay_angles.py`
- Create: `app/tools/magic_erase.py`
- Create: `app/tools/inpaint.py`
- Create: `app/tools/relight_shadows.py`
- Create: `app/tools/upscale_4k.py`
- Create: `app/tools/resize_outpaint.py`
- Create: `app/tools/product_motion.py`

- [ ] **Step 1: Create `app/tools/product_photoshoot.py`**

```python
"""product_photoshoot — the core "stage a product photo, generate" tool.
Routes to MockAIProvider for now, same as every other tool. See
on_model_shots.py for the pattern this file follows. input_payload (from
the frontend): { prompt, mode: "precise"|"creative",
aspect: "1:1"|"4:5"|"16:9"|"9:16", variations: 1-8, brand_kit_on: bool } —
unvalidated for now, per BACKEND-NEEDS.md's explicit recommendation (no real
AIProvider exists yet to dictate a required shape).
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="product_photoshoot",
        display_name="Product Photoshoot",
        output_media_type="image",
        provider=ai_provider,
    )
)
```

- [ ] **Step 2: Create `app/tools/background_swap.py`**

```python
"""background_swap — replaces a product shot's background. Routes to
MockAIProvider for now, same as every other tool. input_payload:
{ prompt, aspect: "1:1"|"4:5"|"16:9"|"9:16" }.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="background_swap",
        display_name="Background Swap",
        output_media_type="image",
        provider=ai_provider,
    )
)
```

- [ ] **Step 3: Create `app/tools/mockup_studio.py`**

```python
"""mockup_studio — places a design onto an apparel/packaging/device mockup.
Routes to MockAIProvider for now, same as every other tool. input_payload:
{ mockup_type: "apparel"|"packaging"|"device", prompt }.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="mockup_studio",
        display_name="Mockup Studio",
        output_media_type="image",
        provider=ai_provider,
    )
)
```

- [ ] **Step 4: Create `app/tools/flat_lay_angles.py`**

```python
"""flat_lay_angles — generates additional flat-lay/angle shots of a
product. Routes to MockAIProvider for now, same as every other tool.
input_payload: { angle_count: 1-4 }.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="flat_lay_angles",
        display_name="Flat Lay / Angles",
        output_media_type="image",
        provider=ai_provider,
    )
)
```

- [ ] **Step 5: Create `app/tools/magic_erase.py`**

```python
"""magic_erase — removes a brushed-out region of an image. Routes to
MockAIProvider for now, same as every other tool. input_payload:
{ mask_data_url, strength: 0-100, feather_px } — the frontend sends the
brush mask as a base64 data URL since there's no "upload a second file
alongside the request" shape in /generate today (see BACKEND-NEEDS.md's
note on mask-based tools; revisit as a real Asset with kind="mask" only if
payload size becomes a real problem).
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="magic_erase",
        display_name="Magic Erase",
        output_media_type="image",
        provider=ai_provider,
    )
)
```

- [ ] **Step 6: Create `app/tools/inpaint.py`**

```python
"""inpaint — replaces a brushed-in region of an image with prompted
content. Routes to MockAIProvider for now, same as every other tool.
input_payload: { mask_data_url, prompt } — same mask-as-data-url note as
magic_erase.py.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="inpaint",
        display_name="Inpaint",
        output_media_type="image",
        provider=ai_provider,
    )
)
```

- [ ] **Step 7: Create `app/tools/relight_shadows.py`**

```python
"""relight_shadows — re-lights a product shot and adjusts its shadows.
Routes to MockAIProvider for now, same as every other tool. input_payload:
{ key_angle_deg, softness: "soft"|"hard", warmth_k }.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="relight_shadows",
        display_name="Relight & Shadows",
        output_media_type="image",
        provider=ai_provider,
    )
)
```

- [ ] **Step 8: Create `app/tools/upscale_4k.py`**

```python
"""upscale_4k — upscales an image to 4K. Routes to MockAIProvider for now,
same as every other tool. input_payload: { target_px: 4096 }. Marking this
PRO-only (per BACKEND-NEEDS.md) is deferred until a plan-gating system
exists — nothing enforces it yet.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="upscale_4k",
        display_name="Upscale 4K",
        output_media_type="image",
        provider=ai_provider,
    )
)
```

- [ ] **Step 9: Create `app/tools/resize_outpaint.py`**

```python
"""resize_outpaint — extends an image's canvas via outpainting. Routes to
MockAIProvider for now, same as every other tool. input_payload:
{ direction: "all"|"horizontal"|"vertical", amount_pct }.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="resize_outpaint",
        display_name="Resize & Outpaint",
        output_media_type="image",
        provider=ai_provider,
    )
)
```

- [ ] **Step 10: Create `app/tools/product_motion.py`**

```python
"""product_motion — generates a short product motion clip (orbit, push-in,
pour, unbox, etc). Routes to MockAIProvider for now, same as every other
tool. Also backs the UGC tab's "Effect Templates" tile — that's this same
feature_type with a specific `motion` preset, not a separate registration.
input_payload: { motion: "orbit"|"push-in"|"pan"|"zoom-out"|"pour"|"unbox",
aspect: "9:16"|"16:9", duration_s: 5, notes }.
"""

from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="product_motion",
        display_name="Product Motion",
        output_media_type="video",
        provider=ai_provider,
    )
)
```

- [ ] **Step 11: Run test to verify it passes**

Run: `./venv/Scripts/python.exe -m pytest tests/test_category_a_tools.py -v`
Expected: PASS (2 passed)

- [ ] **Step 12: Run the full existing test suite to check nothing else broke**

Run: `./venv/Scripts/python.exe -m pytest -v`
Expected: all tests PASS (registering 10 new tools must not affect existing routes/tests — `register()` raises loudly on a duplicate `feature_type`, so a collision would show up as a startup/import error here, not a silent bug)

- [ ] **Step 13: Commit**

```bash
git add app/tools/product_photoshoot.py app/tools/background_swap.py app/tools/mockup_studio.py app/tools/flat_lay_angles.py app/tools/magic_erase.py app/tools/inpaint.py app/tools/relight_shadows.py app/tools/upscale_4k.py app/tools/resize_outpaint.py app/tools/product_motion.py
git commit -m "feat(tools): register 10 Category-A tools

product_photoshoot, background_swap, mockup_studio, flat_lay_angles,
magic_erase, inpaint, relight_shadows, upscale_4k, resize_outpaint,
product_motion — all route through MockAIProvider, same as
on_model_shots/ugc. Makes /generate and /generate/bulk work for the
Photoshoot, Refine, and Video/Motion Studio screens.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Seed correct credit costs via a data-only migration

**Files:**
- Create: `alembic/versions/<new-revision-id>_seed_category_a_tool_costs.py`

- [ ] **Step 1: Generate a revision file**

Run: `./venv/Scripts/python.exe -m alembic revision -m "seed category a tool costs"`
Expected: prints the new file path in `alembic/versions/`, `down_revision` auto-set to the current head (`3adad199e5b6`).

- [ ] **Step 2: Replace the generated file's contents**

Open the generated file and replace its body with (keep its auto-generated
`revision`/`down_revision` values at the top — do not overwrite those):

```python
"""seed category a tool costs

Revision ID: <keep-the-generated-id>
Revises: 3adad199e5b6
Create Date: <keep-the-generated-date>

Data-only, same pattern as 3adad199e5b6_register_product_import_as_a_.
The app/tools/ registry (app/tools/product_photoshoot.py etc.) will
auto-insert these rows on first boot via sync_tools_to_db() too, but with
credit_cost defaulted to 1 (the Tool model's column default) since
credit_cost is DB-owned and sync never sets it. Pre-inserting here
guarantees product_motion starts at its real cost (4) instead of silently
starting at 1 and needing a manual correction after the fact. Guarded by
existence checks so re-running (or running after the app has already
auto-inserted a row) is a no-op, not a duplicate-key error.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "<keep-the-generated-id>"
down_revision: Union[str, Sequence[str], None] = "3adad199e5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TOOLS = [
    # (feature_type, display_name, output_media_type, credit_cost)
    ("product_photoshoot", "Product Photoshoot", "image", 1),
    ("background_swap", "Background Swap", "image", 1),
    ("mockup_studio", "Mockup Studio", "image", 1),
    ("flat_lay_angles", "Flat Lay / Angles", "image", 1),
    ("magic_erase", "Magic Erase", "image", 1),
    ("inpaint", "Inpaint", "image", 1),
    ("relight_shadows", "Relight & Shadows", "image", 1),
    ("upscale_4k", "Upscale 4K", "image", 1),
    ("resize_outpaint", "Resize & Outpaint", "image", 1),
    ("product_motion", "Product Motion", "video", 4),
]


def upgrade() -> None:
    conn = op.get_bind()
    for feature_type, display_name, media_type, cost in TOOLS:
        existing = conn.execute(
            sa.text("SELECT 1 FROM tools WHERE feature_type = :ft"), {"ft": feature_type}
        ).first()
        if existing:
            continue
        conn.execute(sa.text("""
            INSERT INTO tools (feature_type, display_name, output_media_type, credit_cost, is_active, created_at, updated_at)
            VALUES (:ft, :name, :media_type, :cost, true, now(), now())
        """), {"ft": feature_type, "name": display_name, "media_type": media_type, "cost": cost})


def downgrade() -> None:
    conn = op.get_bind()
    for feature_type, _, _, _ in TOOLS:
        conn.execute(sa.text("DELETE FROM tools WHERE feature_type = :ft"), {"ft": feature_type})
```

- [ ] **Step 3: Apply the migration to the local dev DB**

Run: `./venv/Scripts/python.exe -m alembic upgrade head`
Expected: prints `Running upgrade 3adad199e5b6 -> <new-id>, seed category a tool costs`

- [ ] **Step 4: Verify the seeded rows by hand**

Run: `./venv/Scripts/python.exe -c "from app.core.db import SessionLocal; from app.models.tool import Tool; db = SessionLocal(); rows = db.query(Tool).filter(Tool.feature_type.in_(['product_motion','magic_erase'])).all(); print([(r.feature_type, r.credit_cost, r.output_media_type) for r in rows])"`
Expected: `[('magic_erase', 1, 'image'), ('product_motion', 4, 'video')]` (order may vary)

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "feat(tools): seed correct credit costs for category A tools

Data-only migration so product_motion starts at 4 credits (not the
default 1) from first boot, following the existing product_import
migration's pattern.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Manual end-to-end verification against the running API

**Files:** none (verification only)

- [ ] **Step 1: Start the API** (if not already running)

Run: `./venv/Scripts/python.exe -m uvicorn app.main:app --reload`
Expected: starts without error; console shows no `[tools] sync_tools_to_db failed` line.

- [ ] **Step 2: Confirm all 10 tools are discoverable**

Run (in another terminal): `curl.exe http://localhost:8000/tools`
Expected: JSON array including all 10 new `feature_type` values alongside `on_model_shots`/`ugc`, `product_motion` with `"credit_cost": 4`, the rest with `"credit_cost": 1`.

- [ ] **Step 3: Stop the server**

Ctrl+C in the terminal running uvicorn (don't leave it running — see README's note about one instance at a time).

---

## Self-Review Notes

- **Spec coverage:** Category A section of the spec is fully covered — all 10 files, the data migration, `input_payload` left unvalidated, `upscale_4k` PRO-gating explicitly deferred (Step comments say so), no route/schema changes made (none needed).
- **Placeholder scan:** No TBD/TODO; the two `<keep-the-generated-id>` and `<keep-the-generated-date>` placeholders are intentional — they're filled in by `alembic revision`'s own output, not left for the engineer to invent.
- **Type consistency:** `ToolSpec(feature_type=, display_name=, output_media_type=, provider=)` matches `app/tools/registry.py`'s dataclass exactly across all 10 files; migration's `TOOLS` tuple order matches the INSERT's named params.
