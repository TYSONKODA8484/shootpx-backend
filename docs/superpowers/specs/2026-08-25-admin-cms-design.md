# Spec — Admin CMS (internal control panel)

**Status:** Ready for review

## Why

There's no way today to look at the system as a whole — how many users signed
up, what teams exist, who's on what plan, what a tool actually costs — without
querying the database by hand. And there's no way to change any of it (plan
pricing/limits, a tool's credit cost, a stuck user's team) without a manual
SQL statement. This spec adds an internal control panel: view everything,
edit everything that's safe to edit, fast to build, not customer-facing.

Two new pieces: a `/cms/*` API surface on this backend, and a small Next.js
app (new `cms/` folder) that talks to it. Explicitly a v1 — full CRUD over
every entity, no fancy workflow, built to be extended later rather than to be
final.

## Section 1 — Auth

A single shared password (`CMS_ADMIN_PASSWORD` env var), not a per-user admin
role — there's no admin-role concept anywhere in this codebase today, and a
shared password is enough for one person testing/operating this alone.

- `POST /cms/login` — body `{"password": "..."}`. Checks against
  `settings.CMS_ADMIN_PASSWORD`. On success, sets a `cms_session` cookie:
  signed with `itsdangerous` exactly like the existing user session cookie
  (`app/core/security.py`), just a different salt (`"cms_session"` instead of
  `"session"`) and its own settings
  (`CMS_SESSION_MAX_AGE_SECONDS`, default 7 days) — same mechanism, not a new
  one.
- `POST /cms/logout` — deletes the cookie.
- `GET /cms/me` — `{"authenticated": true}` or 401; lets the frontend check
  session state on load without hitting a real data endpoint.
- `get_current_admin(request)` — new dependency in
  `app/middleware/cms_auth.py`, mirroring `get_current_user`
  (`app/middleware/auth.py`) but reading `cms_session` and returning nothing
  but a 401 on failure (no user object — there's no per-admin identity here).
  Every `/cms/entities/*` route depends on this.
- Wrong password: 401. No lockout/rate-limiting in v1 — noted as a gap, not
  solved here (single shared password, low stakes, add if this ever moves
  off localhost).

## Section 2 — Entity registry (backend)

One generic CRUD layer instead of 16 hand-written sets of endpoints — same
"a registry every module registers itself into" pattern this codebase
already uses for tools (`app/tools/registry.py`).

```python
# app/core/cms_registry.py
@dataclass(frozen=True)
class FieldConfig:
    name: str
    kind: Literal["string", "int", "bool", "float", "datetime", "json", "enum", "fk"]
    editable: bool = True          # False for code-owned / computed fields
    enum_values: list[str] | None = None   # for kind="enum"
    fk_entity: str | None = None           # for kind="fk" — which registered entity it points to

@dataclass(frozen=True)
class EntityConfig:
    name: str                      # url slug, e.g. "users"
    model: type                    # the SQLAlchemy model class
    label: str                     # display name, e.g. "Users"
    fields: list[FieldConfig]
    search_fields: list[str] = ()  # columns matched by the table's search box
    cache_namespace: str | None = None  # cleared (app.core.cache) after any write

ENTITIES: dict[str, EntityConfig] = {}
def register(entity: EntityConfig) -> None: ...
```

Registered entities (16 — every mapped model in `app/models/`):

| Entity | Model | Notes |
|---|---|---|
| `users` | `User` | `cache_namespace="login"` — an edit here must clear the same cache `get_current_user` reads, or a stale row keeps serving after the edit (same class of bug discussed for `/auth/logout`) |
| `teams` | `Team` | |
| `team-memberships` | `TeamMembership` | role editable (enum: `TeamRole`) — lets support move an owner/change roles by hand |
| `team-invites` | `TeamInvite` | |
| `plans` | `Plan` | `price`, `credit_allowance`, `max_team_members`, `billing_cycle` (enum) all editable — this is the "define pricing/free tier" control |
| `team-subscriptions` | `TeamSubscription` | `status` (enum), `plan_id` (fk), `current_period_end` editable — support tool for stuck subscriptions |
| `team-credit-balances` | `TeamCreditBalance` | editable `balance` — flagged in the UI as "bypasses `credit_transactions` — use `credit-transactions` for an auditable adjustment instead unless you're fixing a desync" |
| `credit-transactions` | `CreditTransaction` | append-only ledger; **create-only** in the UI (no edit/delete) — matches its role as an audit trail |
| `credit-packs` | `CreditPack` | |
| `tools` | `Tool` | `feature_type`/`display_name`/`output_media_type` **read-only** (code-owned, re-synced on every boot — see Section 4); `credit_cost`/`pricing_config`/`is_active` editable — this is the "pricing per feature type" control |
| `ai-models` | `AIModel` | |
| `assets` | `Asset` | `cache_namespace="media"` |
| `generation-jobs` | `GenerationJob` | mostly read-only in practice (worker-owned fields) but not locked down in v1 — editable like everything else, just not a normal thing to hand-edit |
| `product-imports` | `ProductImport` | |
| `payments` | `Payment` | |
| `templates` | `Template` | |

`id` and `created_at`/`updated_at` are always `editable=False` across every
entity — visible for reference, never writable, on every entity regardless of
its own config.

## Section 3 — Backend routes

All under `/cms`, all behind `get_current_admin`:

- `GET /cms/entities` — the registry above, serialized (name, label, fields +
  kinds + editable + enum_values), so the frontend renders tables/forms
  generically instead of hand-coding 16 pages.
- `GET /cms/entities/{entity}?page=&search=` — paginated list (50/page),
  `search` matches `search_fields` with `ILIKE`. 404 if `{entity}` isn't
  registered.
- `POST /cms/entities/{entity}` — create.
- `GET /cms/entities/{entity}/{id}` — one row.
- `PATCH /cms/entities/{entity}/{id}` — partial update; rejects (400) any
  field in the payload that isn't `editable`. Runs `cache_namespace`
  invalidation after commit if the entity declares one.
- `DELETE /cms/entities/{entity}/{id}` — hard delete. A FK-constraint
  violation (e.g. deleting a `Team` that still has memberships) surfaces as a
  400 with the DB's own error text rather than cascading — deliberate for v1,
  see Section 6.
- `GET /cms/stats` — dashboard counts: total users, total teams, active
  subscriptions by plan, total credit balance across all teams. A handful of
  `COUNT(*)`/`GROUP BY` queries, not a generic thing — hand-written since
  "how many people are there" is a specific question, not a generic one.

New file `app/routes/cms_routes.py`; business logic (the generic
list/get/create/update/delete against `EntityConfig`) in
`app/controllers/cms_controller.py`. Mounted in `main.py` next to the other
routers. Kept entirely separate from the existing `admin_routes.py`
(dev-only cache-clear + public `/tools`) — different purpose, different auth.

## Section 4 — The `tools` entity's read-only fields

`Tool.feature_type`/`display_name`/`output_media_type` are re-synced from
`app/tools/*.py`'s registry on every server boot (`sync_tools_to_db`,
called from `main.py`) — see the model's own docstring
(`app/models/tool.py:8-16`). If the CMS let you edit them, the edit would
silently vanish on next restart. So:

- Those three fields are shown, marked read-only in both the API's field
  config and the frontend form (disabled input, not hidden — you should
  still see what they are).
- `credit_cost`, `pricing_config`, `is_active` are the real, permanent
  controls — DB-owned, untouched by the sync once a row exists.
- **Adding a genuinely new tool still requires a new Python module** in
  `app/tools/` (real generation behavior/prompts/provider wiring) — the CMS
  can price and enable/disable it once that module exists and the app has
  restarted (which creates its row via the sync), not before.

## Section 5 — Frontend (`cms/` folder)

New top-level folder, sibling to `app/`. Next.js (App Router) + TypeScript +
Tailwind — plain/functional styling, this is an internal tool, not the
product's UI.

```
cms/
  app/
    login/page.tsx          — password form -> POST /cms/login
    (dashboard)/
      layout.tsx             — sidebar: one link per registered entity + "Overview"
      page.tsx                — GET /cms/stats as a few number tiles
      [entity]/
        page.tsx              — generic table: columns from GET /cms/entities,
                                  rows from GET /cms/entities/{entity}, search
                                  box, pagination, "+ New" button, row click -> edit
        [id]/page.tsx          — generic form built from the same field config;
                                  Save (PATCH), Delete (with confirm dialog)
  lib/
    api.ts                    — fetch wrapper, `credentials: "include"`,
                                 redirects to /login on 401
    fields.tsx                — one input renderer per FieldConfig.kind
                                 (text/number/checkbox/select-for-enum/
                                 select-for-fk/datetime/json textarea)
  README.md                   — how to run it (`npm install && npm run dev`),
                                 how auth works, the full `/cms/*` endpoint
                                 list, required env vars
  .env.example                — NEXT_PUBLIC_BACKEND_URL
```

Read-only fields (`editable=False`) render as disabled inputs in the form —
visible, not editable, not hidden — so it's obvious why `feature_type` won't
save.

## Section 6 — Backend config/CORS changes

- `app/core/config.py`: add `CMS_ADMIN_PASSWORD: str = ""` (must be set —
  empty means `/cms/login` always 401s, fails closed), `CMS_URL: str =
  "http://localhost:3001"`, `CMS_SESSION_MAX_AGE_SECONDS: int = 60*60*24*7`.
- `app/middleware/setup.py`: add `settings.CMS_URL` to `allow_origins` so the
  Next.js app's cookie-credentialed requests aren't blocked by CORS.
- `.env.example`: document the new vars.

## Section 7 — Known gaps (deliberate, not oversights)

- **Hard delete, no cascade handling.** Deleting a row with dependents fails
  loud (400 + DB error) rather than cascading or soft-deleting. Right
  behavior differs per entity (delete a `Team` should probably cascade its
  memberships; delete a `Plan` with active subscribers probably shouldn't be
  allowed at all) — that's real per-entity policy work, out of scope for a
  first "testing" version. You'll hit this as a slightly ugly error message
  before it becomes a real problem.
- **No audit log of CMS edits.** Every write just happens; nothing records
  who changed what, when (there's no "who" anyway — shared password, not
  per-admin login). Fine for solo use; would need real admin accounts before
  this matters.
- **No rate-limiting/lockout on `/cms/login`.** Low stakes on localhost;
  revisit if this is ever exposed beyond your own machine.
- **`team-credit-balances` editing bypasses the ledger.** Direct edits there
  don't create a matching `credit_transactions` row, so the two can drift
  out of sync with each other. Flagged in the UI; `credit-transactions`
  (create-only) is the auditable way to adjust a balance.

## Section 8 — Testing

Backend: pytest tests for the generic layer against 1–2 representative
entities (e.g. `plans`, `users`) — auth-required (401 without cookie),
list/get/create/patch/delete happy paths, PATCH rejecting a non-editable
field, DELETE surfacing a FK-constraint error as 400. Not exhaustive
per-entity coverage across all 16 — the layer is generic, so once it's
proven correct for two entities the rest follow the same code path. Manual
click-through via the CMS UI covers the rest for v1.

Frontend: no automated tests in v1 (internal tool, fast-moving, manual
verification via the running app) — matches "simple/testing-first."
