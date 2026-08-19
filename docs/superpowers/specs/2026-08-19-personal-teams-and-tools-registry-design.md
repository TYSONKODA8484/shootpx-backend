# Spec A — Personal Teams, Tool Registry Auto-Discovery, Dev Cache API

**Status:** Ready for review
**Depends on:** nothing (this lands first)
**Depended on by:** Spec B (billing) — team creation needs to assign a Free
plan the moment a team exists; the `tools` table this spec creates is what
Spec B's pricing engine extends with model/template pricing.

## Why

Three unrelated frictions, addressed together because they're all small and
touch adjacent files:

1. A brand-new user has zero teams and can't do anything — `team_id` is
   required everywhere but nothing ever creates one automatically.
2. Adding a tool requires editing `app/tools/__init__.py` by hand, and there's
   no DB-editable way to disable a tool or attach a credit cost to it without
   a redeploy.
3. Clearing a cache namespace requires shell access to the server — no API,
   no console button.

## Section 1 — Auto-create a personal team on first-ever signup

**`app/controllers/auth_controller.py`**

`upsert_user_from_firebase(db, decoded_token)` changes its return type from
`User` to `tuple[User, bool]`. The second value, `is_new`, is `True` only when
neither the Firebase uid lookup nor the email-fallback lookup found an
existing row:

```python
user = db.get(User, uid)
if not user:
    user = db.query(User).filter(User.email == email).first()
is_new = user is None          # computed BEFORE the fallback assignment below
if user:
    ...
else:
    user = User(id=uid, email=email, name=name, avatar_url=avatar_url)
    db.add(user)
db.commit()
db.refresh(user)
cache.delete(CACHE_NAMESPACE, user.id)
return user, is_new
```

**`app/controllers/team_controller.py`** — new function, reuses `create_team`:

```python
def create_personal_team(db: Session, user: User) -> Team:
    base_name = user.name or user.email.split("@")[0]
    team, _ = create_team(db, user, TeamCreate(name=f"{base_name}'s Workspace"))
    return team
```

`list_my_teams` gains `.order_by(Team.created_at.asc())` — since the personal
team is always created first, `GET /teams`'s first result is always reliably
theirs. This is what lets the test console (and later a real frontend) safely
default to it without guessing.

**`app/routes/auth_routes.py`** — `POST /auth/session` becomes:

```python
user, is_new = auth_controller.upsert_user_from_firebase(db, decoded)
if is_new:
    team_controller.create_personal_team(db, user)
team_controller.accept_pending_invites(db, user)
```

**No existing API contract changes.** `team_id` stays required everywhere it
is today, on every route. This only guarantees `GET /teams` is never empty.

**Note for Spec B:** once billing exists, `create_personal_team` gains one
more line — assigning the Free plan. Not built here; Spec B extends this
function rather than duplicating it.

## Section 2 — Team rename

New route `PATCH /teams/{id}`, owner-only (reuses `compute_permissions(...).can_manage_team`,
already exists — no new permission logic).

**`app/schemas/teams.py`** — new schema:
```python
class TeamUpdate(BaseModel):
    name: str
    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v): ...   # same validator TeamCreate already has
```

**`app/controllers/team_controller.py`** — new function:
```python
def rename_team(db: Session, team_id: str, current_user: User, payload: TeamUpdate) -> Team:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_manage_team:
        raise HTTPException(403, "Only the team owner can rename this team")
    team = db.get(Team, team_id)
    team.name = payload.name
    db.commit()
    db.refresh(team)
    return team
```

**`app/routes/team_routes.py`** — new route returning `TeamOut`.

## Section 3 — Backfill existing teamless users

New Alembic migration (data-only, via `op.execute` raw SQL — independent of
model code, since models can drift over time):

```python
def upgrade():
    conn = op.get_bind()
    rows = conn.execute(sa.text("""
        SELECT u.id, u.name, u.email FROM users u
        LEFT JOIN team_members tm ON tm.user_id = u.id
        WHERE tm.id IS NULL
    """)).fetchall()
    for user_id, name, email in rows:
        team_id = str(uuid.uuid4())
        team_name = f"{name or email.split('@')[0]}'s Workspace"
        conn.execute(sa.text(
            "INSERT INTO teams (id, name, created_at) VALUES (:id, :name, now())"
        ), {"id": team_id, "name": team_name})
        conn.execute(sa.text(
            "INSERT INTO team_members (id, team_id, user_id, role, joined_at) "
            "VALUES (:id, :team_id, :user_id, 'owner', now())"
        ), {"id": str(uuid.uuid4()), "team_id": team_id, "user_id": user_id})

def downgrade():
    pass  # documented no-op — no flag marks these teams (deliberate, see
          # design discussion), so there's nothing to reliably reverse.
```

## Section 4 — Test console

`test-console/index.html`: after `establishBackendSession()` succeeds (both
Google and email-link paths) and after clicking "Who am I", automatically
call `GET /teams` and pre-fill `asset-team-id-input`, `generate-team-id-input`,
`bulk-team-id-input`, and `team-id-input` with `teams[0]`. The manual override
and the full team list stay exactly as they are — this only changes the
default value on load.

Section 2's copy changes from implying "you must create a team" to reflecting
that one already exists, with create/rename framed as optional actions.

New "Rename team" button next to the existing team controls, calling the new
`PATCH /teams/{id}`.

## Section 5 — Tool registry auto-discovery

**`app/tools/__init__.py`** replaces its hand-written import list with a scan:

```python
import importlib
import pkgutil
from pathlib import Path

_tools_dir = Path(__file__).parent
for _, module_name, _ in pkgutil.iter_modules([str(_tools_dir)]):
    if module_name.startswith("_") or module_name == "registry":
        continue
    importlib.import_module(f"app.tools.{module_name}")

from app.tools.registry import TOOLS, ToolSpec, get_tool, known_feature_types  # noqa: F401
```

`_template.py` stays excluded via the existing underscore convention — no
special-casing needed, it now does double duty. `registry.py` is explicitly
excluded by name since it's the registry, not a tool. A tool can still be a
whole subpackage (a folder with `__init__.py`) — `pkgutil.iter_modules` lists
those the same way it lists flat files, so nothing about "one importable unit
per tool" changes; it's now literally zero-touch outside that one file/folder.

**Net effect: adding a tool is "write the file/folder, restart the server."**
No import line, no route, no schema change, no DB row to add by hand.

## Section 6 — The `tools` DB table

New model, `app/models/tool.py`:

```python
class Tool(Base):
    __tablename__ = "tools"
    feature_type = Column(String, primary_key=True)      # code-owned
    display_name = Column(String, nullable=False)         # code-owned
    output_media_type = Column(String, nullable=False)    # code-owned
    default_model_id = Column(String, nullable=True)
    # ^ code-owned. Set when this tool offers model selection (Spec B).
    #   NULL means this tool has no model concept — falls back to credit_cost
    #   below. This is the one column that ties Spec A's tools table to
    #   Spec B's pricing engine without Spec A needing to know Spec B's
    #   internals. DELIBERATELY NOT a ForeignKey here — ai_models doesn't
    #   exist yet (Spec B creates it). Spec B's migration adds the actual
    #   FK constraint once that table exists; see the sequencing note below.
    credit_cost = Column(Integer, nullable=False, default=1)   # DB-owned
    pricing_config = Column(JSON, nullable=True)                # DB-owned
    # ^ e.g. {"resolution_multipliers": {"2k": 1, "4k": 2}}. Only meaningful
    #   once Spec B's pricing engine reads it; harmless and unused until then.
    is_active = Column(Boolean, nullable=False, default=True)   # DB-owned
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

**`app/tools/sync.py`** (new) — `sync_tools_to_db(db: Session)`, upserts every
`ToolSpec` from the in-memory registry into `tools`, touching only the
code-owned columns on an existing row:

```python
def sync_tools_to_db(db: Session) -> None:
    for spec in TOOLS.values():
        existing = db.get(Tool, spec.feature_type)
        if existing:
            existing.display_name = spec.display_name
            existing.output_media_type = spec.output_media_type
            # credit_cost, pricing_config, is_active, default_model_id
            # are DB-owned — never touched here, so an admin's pricing/
            # toggle decisions survive every restart.
        else:
            db.add(Tool(feature_type=spec.feature_type,
                        display_name=spec.display_name,
                        output_media_type=spec.output_media_type))
    db.commit()
```

Called once from `app/main.py` at startup, wrapped in try/except (logs a
warning, doesn't crash boot — same tolerance philosophy as `init_firebase()`).

**Validation split** — the schema layer and the DB layer check different
things, deliberately:
- `schemas/generation.py` keeps checking the **code** registry
  (`known_feature_types()`) — "does this feature_type exist at all." Unchanged,
  still a 422.
- `generation_controller.py` adds one new check against the **DB**:
  ```python
  tool_row = db.get(Tool, payload.feature_type)
  if tool_row is not None and not tool_row.is_active:
      raise HTTPException(400, f"Tool '{payload.feature_type}' is currently disabled")
  ```
  Fails **open** if the row is somehow missing (defensive — code-registry
  existence is still the hard requirement), fails **closed** only on an
  explicit `is_active = False`.

New Alembic migration: schema-only, autogenerated for the `tools` table (the
FK to `ai_models` is created here but stays nullable/unenforced in practice
until Spec B creates that table — if Spec A ships before Spec B, this
migration should NOT include the FK constraint yet; add it in Spec B's
migration instead, once `ai_models` exists. **Sequencing note:** if built in
order (A then B), split `default_model_id` as a plain nullable String column
here with the FK constraint added by Spec B's migration once `ai_models`
exists.)

## Section 7 — Dev-only cache-clear API

New `app/routes/admin_routes.py` — no separate controller file, this is as
trivial as `health_routes.py`:

```python
router = APIRouter(prefix="/admin", tags=["admin"])

KNOWN_CACHE_NAMESPACES = ["login", "media"]   # new, in core/cache.py

@router.post("/cache/clear")
def clear_cache(namespace: str = Body(embed=True)):
    if settings.ENV != "development":
        raise HTTPException(404)   # 404, not 403 — don't reveal this exists
    if namespace == "all":
        total = sum(cache.clear_namespace(ns) for ns in KNOWN_CACHE_NAMESPACES)
        return {"namespace": "all", "cleared": total}
    if namespace not in KNOWN_CACHE_NAMESPACES:
        raise HTTPException(400, f"Unknown namespace: {namespace!r}")
    return {"namespace": namespace, "cleared": cache.clear_namespace(namespace)}
```

Test console: new section with three buttons — "Clear login cache", "Clear
media cache", "Clear all caches" — each logging the response (including
cleared-key count) to the existing log panel.

## Section 8 — Cleanup: remove `has_team_access()`

`core/permissions.py:47` — confirmed unused (`BOOK.md` Ch. 6 already flags it
⚪ ORPHANED; `get_job_summaries` uses a batched membership query instead).
Delete the function. `BOOK.md`'s Deprecation Ledger entry #7 moves from ⚪
ORPHANED to 🔴 REMOVED, with the removal commit hash filled in once merged.

## Documentation updates required (BOOK.md, append-only)

- **Chapter 6** (Teams, Invites, Permissions): mark 🟡 CHANGED. Keep the
  existing "a team only exists if someone calls POST /teams" paragraph as a
  🔴 blockquote with a "why it went away" note; add the new 🟢 auto-creation
  behavior + the rename endpoint underneath.
- **Chapter 12** (Tool Registry): mark 🟡 CHANGED. Keep the "add one import
  line to `__init__.py`" step documented as 🔴 (superseded); add the
  auto-discovery mechanism as 🟢, plus a new subsection on the `tools` table.
- **Chapter 15** (Caching): add a new subsection documenting the admin
  cache-clear endpoint (🟢, new — nothing to mark deprecated here).
- **Timeline** (Part IV): one new entry, this spec's implementation.
- **Deprecation Ledger** (Part V): entry #7 (`has_team_access`) updated from
  ⚪ to 🔴; new entry for "manual `POST /teams` as the only way to get a team."
- **Appendix A** (File Map): add `app/models/tool.py`, `app/tools/sync.py`,
  `app/routes/admin_routes.py`.
- **Appendix B** (Every Route): add `PATCH /teams/{id}`, `POST /admin/cache/clear`.
- `README.md` / `DESIGN.md`: one paragraph each on personal-team-on-signup,
  new routes added to their route tables.

## Verification plan

No automated suite exists in this repo (consistent with everything else) —
manual verification, same rigor as `scripts/test_pipeline.py`:

1. Sign up a brand-new account → `GET /teams` returns exactly one team named
   `"<name>'s Workspace"`, owner role.
2. Immediately call `/generate` with that `team_id` and an uploaded asset —
   no `POST /teams` call needed anywhere first.
3. `PATCH /teams/{id}` as owner → name updates; as non-owner → 403.
4. Run the backfill migration against a test row with zero teams → confirms
   a team + membership appears.
5. Add a new tool file with no `__init__.py` edit → restart → `known_feature_types()`
   includes it → a `tools` row appears automatically on next boot.
6. Flip a tool's `is_active` to `false` directly in the DB → `/generate`
   with that `feature_type` now returns 400, while the schema-level 422 for
   a genuinely unknown `feature_type` still works separately.
7. `POST /admin/cache/clear` works with `ENV=development`; returns 404 with
   any other `ENV` value.
8. Click through the test console end to end on a fresh browser profile —
   all four `team_id` fields pre-filled without ever touching "Create team".

## Non-goals (this spec)

- Deleting a team, leaving a team — no such endpoints exist today; out of scope.
- Any credit/billing logic — that's Spec B, which extends `create_personal_team`
  and the `tools` table this spec creates.
- Admin auth beyond "dev environment only" — a real admin-role system is a
  separate, future decision if the cache API (or others like it) ever need to
  run in production.
