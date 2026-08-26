# B3 — Templates Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /templates` — a public catalog of real, seeded template rows (24, across Photoshoot/Mockup/On-model/Motion/UGC) that the Templates page and Home's template strip can list and apply.

**Architecture:** The `templates` table already exists (Chapter 17) but is missing the columns `GET /templates` needs to display (`name`, `category`, `preview_asset_url`) and has zero rows. One schema migration adds the columns; one data migration seeds 24 real rows, each tied to a real `feature_type` with a `preset_payload` matching that tool's documented `input_payload` shape. New `schemas/templates.py`, `template_controller.py`, `template_routes.py` — no auth (public catalog data, same spirit as `GET /tools`).

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, pytest.

---

### Task 1: Add `name`/`category`/`preview_asset_url` to the `Template` model

**Files:**
- Modify: `app/models/template.py`
- Create: `alembic/versions/7e11343179fd_add_name_category_preview_asset_url_to_.py` (via autogenerate)

- [x] **Step 1: Add the columns to the model**

In `app/models/template.py`, insert right after `id = Column(String, primary_key=True, default=new_id)`:

```python
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)  # "Photoshoot" | "Mockup" |
    # "On-model" | "Motion" | "UGC" — a plain string, not an enum, same
    # lightweight-string convention as GenerationJob.feature_type/batch_id.
    preview_asset_url = Column(String, nullable=True)  # null until a real
    # preview image exists for this template — seeding a fake URL would be
    # dishonest catalog data (see BACKEND-NEEDS.md's B3 section).
```

- [x] **Step 2: Confirm the `templates` table is empty before adding non-nullable columns**

Run: `./venv/Scripts/python.exe -c "from app.core.db import SessionLocal; import sqlalchemy as sa; db = SessionLocal(); print(db.execute(sa.text('SELECT COUNT(*) FROM templates')).scalar()); db.close()"`
Expected: `0` (if not 0, `name`/`category` need a default backfilled in the migration before the `NOT NULL` constraint — not needed at spec time).

- [x] **Step 3: Autogenerate and apply the migration**

Run: `./venv/Scripts/python.exe -m alembic revision --autogenerate -m "add name category preview_asset_url to templates"`
Then read the generated file in `alembic/versions/` and confirm it only adds the 3 columns (nothing unrelated).
Run: `./venv/Scripts/python.exe -m alembic upgrade head`

- [x] **Step 4: Run the full suite**

Run: `./venv/Scripts/python.exe -m pytest`
Expected: all passing (adding nullable/non-nullable columns to an empty table doesn't affect any existing model usage)

- [x] **Step 5: Commit**

```bash
git add app/models/template.py alembic/versions/
git commit -m "feat(templates): add name/category/preview_asset_url columns

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `schemas/templates.py`

**Files:**
- Create: `app/schemas/templates.py`

- [ ] **Step 1: Create the schema file**

```python
from typing import Any

from pydantic import BaseModel


class TemplateOut(BaseModel):
    id: str
    name: str
    category: str
    feature_type: str
    credit_cost: int
    preview_asset_url: str | None
    input_payload_preset: dict[str, Any]

    class Config:
        from_attributes = True


class TemplateListOut(BaseModel):
    total: int
    templates: list[TemplateOut]
```

- [ ] **Step 2: Commit**

```bash
git add app/schemas/templates.py
git commit -m "feat(templates): add template catalog schemas

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `template_controller.list_templates`

**Files:**
- Create: `app/controllers/template_controller.py`
- Test: `tests/test_templates_catalog.py`

- [ ] **Step 1: Write the failing tests**

```python
"""tests/test_templates_catalog.py — GET /templates' filter/search/cost
logic."""

from app.controllers import template_controller
from app.models.template import Template
from app.models.team import new_id
from app.models.tool import Tool


def _tool(db, feature_type="product_photoshoot", credit_cost=1):
    tool = db.get(Tool, feature_type)
    if tool is None:
        tool = Tool(feature_type=feature_type, display_name=feature_type, output_media_type="image", credit_cost=credit_cost)
        db.add(tool)
        db.commit()
    return tool


def _template(db, *, name, category, feature_type, preset=None, credit_cost_override=None, is_active=True):
    tpl = Template(
        id=new_id(), name=name, category=category, feature_type=feature_type,
        preset_payload=preset or {}, credit_cost_override=credit_cost_override, is_active=is_active,
    )
    db.add(tpl)
    db.commit()
    return tpl


def test_list_templates_returns_total_and_rows(db_session):
    _tool(db_session)
    _template(db_session, name="Wet Stone Ledge", category="Photoshoot", feature_type="product_photoshoot")

    result = template_controller.list_templates(db_session)

    assert result.total == 1
    assert result.templates[0].name == "Wet Stone Ledge"


def test_list_templates_filters_by_category(db_session):
    _tool(db_session)
    _template(db_session, name="Wet Stone Ledge", category="Photoshoot", feature_type="product_photoshoot")
    _template(db_session, name="Apparel Tee Front", category="Mockup", feature_type="product_photoshoot")

    result = template_controller.list_templates(db_session, category="Mockup")

    assert result.total == 1
    assert result.templates[0].category == "Mockup"


def test_list_templates_search_is_case_insensitive_substring(db_session):
    _tool(db_session)
    _template(db_session, name="Wet Stone Ledge", category="Photoshoot", feature_type="product_photoshoot")
    _template(db_session, name="Marble Vanity", category="Photoshoot", feature_type="product_photoshoot")

    result = template_controller.list_templates(db_session, q="stone")

    assert result.total == 1
    assert result.templates[0].name == "Wet Stone Ledge"


def test_list_templates_credit_cost_uses_override_when_set(db_session):
    _tool(db_session, credit_cost=1)
    _template(db_session, name="Wet Stone Ledge", category="Photoshoot", feature_type="product_photoshoot", credit_cost_override=3)

    result = template_controller.list_templates(db_session)

    assert result.templates[0].credit_cost == 3


def test_list_templates_credit_cost_falls_back_to_tool_cost(db_session):
    _tool(db_session, credit_cost=4)
    _template(db_session, name="360 Orbit", category="Motion", feature_type="product_photoshoot")

    result = template_controller.list_templates(db_session)

    assert result.templates[0].credit_cost == 4


def test_list_templates_excludes_inactive(db_session):
    _tool(db_session)
    _template(db_session, name="Retired Preset", category="Photoshoot", feature_type="product_photoshoot", is_active=False)

    result = template_controller.list_templates(db_session)

    assert result.total == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/Scripts/python.exe -m pytest tests/test_templates_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.controllers.template_controller'`

- [ ] **Step 3: Implement `app/controllers/template_controller.py`**

```python
"""Public template catalog — no auth, same spirit as GET /tools. A template
is a preset FOR a tool (its feature_type), not its own generation path —
applying one just pre-fills that tool's input_payload before the user
tweaks and hits /generate.
"""

from sqlalchemy.orm import Session

from app.models.template import Template
from app.models.tool import Tool
from app.schemas.templates import TemplateListOut, TemplateOut


def _effective_cost(template: Template, tool: Tool | None) -> int:
    if template.credit_cost_override is not None:
        return template.credit_cost_override
    return tool.credit_cost if tool else 1


def list_templates(
    db: Session,
    category: str | None = None,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> TemplateListOut:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    query = db.query(Template).filter(Template.is_active == True)  # noqa: E712
    if category:
        query = query.filter(Template.category == category)
    if q:
        query = query.filter(Template.name.ilike(f"%{q}%"))

    total = query.count()
    rows = query.order_by(Template.category, Template.name).offset(offset).limit(limit).all()

    feature_types = {t.feature_type for t in rows}
    tools_by_type = (
        {t.feature_type: t for t in db.query(Tool).filter(Tool.feature_type.in_(feature_types)).all()}
        if feature_types else {}
    )

    templates = [
        TemplateOut(
            id=t.id, name=t.name, category=t.category, feature_type=t.feature_type,
            credit_cost=_effective_cost(t, tools_by_type.get(t.feature_type)),
            preview_asset_url=t.preview_asset_url, input_payload_preset=t.preset_payload,
        )
        for t in rows
    ]
    return TemplateListOut(total=total, templates=templates)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/Scripts/python.exe -m pytest tests/test_templates_catalog.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Run the full suite**

Run: `./venv/Scripts/python.exe -m pytest`
Expected: all passing

- [ ] **Step 6: Commit**

```bash
git add app/controllers/template_controller.py tests/test_templates_catalog.py
git commit -m "feat(templates): add list_templates controller

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Route + wire into `main.py`

**Files:**
- Create: `app/routes/template_routes.py`
- Modify: `app/main.py`

- [ ] **Step 1: Create the route**

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers import template_controller
from app.core.db import get_db
from app.schemas.templates import TemplateListOut

router = APIRouter(tags=["templates"])


@router.get("/templates", response_model=TemplateListOut)
def list_templates(
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=20, le=100, gt=0),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return template_controller.list_templates(db, category=category, q=q, limit=limit, offset=offset)
```

- [ ] **Step 2: Wire into `app/main.py`**

Add the import alongside the other route imports:

```python
from app.routes.template_routes import router as template_router
```

Add the include (right after `app.include_router(product_import_router)`):

```python
app.include_router(template_router)
```

- [ ] **Step 3: Run the full suite**

Run: `./venv/Scripts/python.exe -m pytest`
Expected: all passing

- [ ] **Step 4: Commit**

```bash
git add app/routes/template_routes.py app/main.py
git commit -m "feat(templates): add GET /templates route

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Seed 24 real templates

**Files:**
- Create: `alembic/versions/<new-revision-id>_seed_templates_catalog.py`

- [ ] **Step 1: Generate a revision file**

Run: `./venv/Scripts/python.exe -m alembic revision -m "seed templates catalog"`

- [ ] **Step 2: Replace the generated file's contents**

(keep the auto-generated `revision`/`down_revision`/`Create Date` values)

```python
"""seed templates catalog

Revision ID: <keep-the-generated-id>
Revises: 7e11343179fd
Create Date: <keep-the-generated-date>

Data-only. Seeds 24 real templates across the 5 categories the Studio's
Templates page and Home's template strip need (BACKEND-NEEDS.md's B3:
"even 20-30 real seeded rows makes the page honest instead of empty").
preview_asset_url is left NULL for all of them — no real preview images
exist yet; seeding a fake URL would be dishonest catalog data.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "<keep-the-generated-id>"
down_revision: Union[str, Sequence[str], None] = "7e11343179fd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEMPLATES = [
    # (name, category, feature_type, preset_payload)
    ("Wet Stone Ledge", "Photoshoot", "product_photoshoot", {"prompt": "wet stone ledge, cold morning light", "aspect": "1:1", "mode": "creative"}),
    ("Marble Vanity", "Photoshoot", "product_photoshoot", {"prompt": "white marble vanity counter, soft daylight", "aspect": "4:5", "mode": "precise"}),
    ("Sandy Dune Backdrop", "Photoshoot", "product_photoshoot", {"prompt": "sand dune backdrop, golden hour", "aspect": "1:1", "mode": "creative"}),
    ("Studio Seamless White", "Photoshoot", "product_photoshoot", {"prompt": "seamless white studio backdrop, softbox lighting", "aspect": "1:1", "mode": "precise"}),
    ("Concrete Loft", "Photoshoot", "product_photoshoot", {"prompt": "raw concrete loft interior, natural window light", "aspect": "16:9", "mode": "creative"}),
    ("Apparel Tee Front", "Mockup", "mockup_studio", {"mockup_type": "apparel", "prompt": "unisex crewneck t-shirt, front view, studio lighting"}),
    ("Kraft Box Packaging", "Mockup", "mockup_studio", {"mockup_type": "packaging", "prompt": "kraft cardboard box mockup on wooden table"}),
    ("Phone Case Device", "Mockup", "mockup_studio", {"mockup_type": "device", "prompt": "smartphone case mockup, hand holding phone"}),
    ("Tote Bag Apparel", "Mockup", "mockup_studio", {"mockup_type": "apparel", "prompt": "canvas tote bag mockup, flat lay"}),
    ("Glass Jar Packaging", "Mockup", "mockup_studio", {"mockup_type": "packaging", "prompt": "glass jar label mockup, clean white background"}),
    ("Studio Fashion Model", "On-model", "on_model_shots", {"prompt": "studio fashion editorial, plain grey background"}),
    ("Street Style Model", "On-model", "on_model_shots", {"prompt": "street style, urban background, natural light"}),
    ("Outdoor Lifestyle Model", "On-model", "on_model_shots", {"prompt": "outdoor lifestyle, golden hour, casual pose"}),
    ("Minimal Studio Model", "On-model", "on_model_shots", {"prompt": "minimal studio backdrop, soft shadows"}),
    ("Editorial Runway Model", "On-model", "on_model_shots", {"prompt": "editorial runway pose, dramatic lighting"}),
    ("360 Orbit", "Motion", "product_motion", {"motion": "orbit", "aspect": "9:16", "duration_s": 5}),
    ("Push-In Reveal", "Motion", "product_motion", {"motion": "push-in", "aspect": "16:9", "duration_s": 5}),
    ("Slow Pan", "Motion", "product_motion", {"motion": "pan", "aspect": "16:9", "duration_s": 5}),
    ("Zoom Out Reveal", "Motion", "product_motion", {"motion": "zoom-out", "aspect": "9:16", "duration_s": 5}),
    ("Pour Splash", "Motion", "product_motion", {"motion": "pour", "aspect": "9:16", "duration_s": 5}),
    ("Unbox Reveal", "Motion", "product_motion", {"motion": "unbox", "aspect": "9:16", "duration_s": 5}),
    ("Testimonial Selfie", "UGC", "ugc", {"prompt": "handheld selfie style testimonial, natural lighting"}),
    ("Unboxing Reaction", "UGC", "ugc", {"prompt": "unboxing reaction, excited expression, home setting"}),
    ("Before/After Demo", "UGC", "ugc", {"prompt": "before and after demo, split screen style"}),
]


def upgrade() -> None:
    conn = op.get_bind()
    for name, category, feature_type, preset in TEMPLATES:
        existing = conn.execute(
            sa.text("SELECT 1 FROM templates WHERE name = :name"), {"name": name}
        ).first()
        if existing:
            continue
        conn.execute(sa.text("""
            INSERT INTO templates (id, name, category, feature_type, preset_payload, is_active)
            VALUES (:id, :name, :category, :ft, :preset, true)
        """), {
            "id": str(uuid.uuid4()), "name": name, "category": category,
            "ft": feature_type, "preset": sa.text("CAST(:preset_json AS JSON)").bindparams(preset_json=__import__("json").dumps(preset)) if False else preset,
        })


def downgrade() -> None:
    conn = op.get_bind()
    for name, _category, _ft, _preset in TEMPLATES:
        conn.execute(sa.text("DELETE FROM templates WHERE name = :name"), {"name": name})
```

**Note before running:** the inline `CAST(:preset_json AS JSON)` fallback
above is dead code (guarded by `if False`) left in from drafting — the
`preset` dict is passed directly as a bind parameter. Confirm this actually
works against Postgres's JSON column type in Step 3 below; if the driver
rejects a raw Python `dict` bind parameter for a `JSON` column, switch to
`sa.text(...).bindparams(sa.bindparam("preset", type_=sa.JSON))` and pass
the dict through that bind, or use SQLAlchemy Core's `table()`/`insert()`
construct instead of raw `text()` for this one column. Report back if this
adjustment is needed — don't silently paper over an insert that fails.

- [ ] **Step 3: Apply the migration**

Run: `./venv/Scripts/python.exe -m alembic upgrade head`
Expected: prints the upgrade line with no errors. If it errors on the
`preset_payload` bind, fix per the note above, then re-run.

- [ ] **Step 4: Verify the seeded rows**

Run: `./venv/Scripts/python.exe -c "from app.core.db import SessionLocal; import sqlalchemy as sa; db = SessionLocal(); print(db.execute(sa.text('SELECT COUNT(*), COUNT(DISTINCT category) FROM templates')).first()); db.close()"`
Expected: `(24, 5)`

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "feat(templates): seed 24 real templates across 5 categories

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Manual end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Start the API**

Run: `./venv/Scripts/python.exe -m uvicorn app.main:app --port 8123`

- [ ] **Step 2: Confirm the catalog is real**

Run: `curl.exe -s "http://localhost:8123/templates?category=Motion"`
Expected: `{"total": 6, "templates": [...]}` — 6 Motion-category templates, each with `feature_type: "product_motion"` and a real `input_payload_preset`.

- [ ] **Step 3: Stop the server**

Ctrl+C.

---

## Self-Review Notes

- **Spec coverage:** schema columns, `GET /templates` with `category`/`q`/pagination, no-auth, 24 seeded rows across 5 categories with real `preset_payload`s tied to real `feature_type`s, `preview_asset_url` left null (not faked) — all covered.
- **Placeholder scan:** the migration's JSON-bind note in Task 5 is a flagged, explained risk with an explicit fallback — not a vague TODO. Confirm during execution which path was needed and note it in the commit if the fallback was used.
- **Type consistency:** `list_templates(db, category=None, q=None, limit=20, offset=0) -> TemplateListOut` matches its route call; `TemplateOut`/`TemplateListOut` field names match between schema and controller construction.
