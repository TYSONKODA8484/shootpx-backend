# ShootPX Backend — Design Notes

Living reference for how this backend is built and why, so future work (by
Claude or by you) starts from the same picture instead of re-deriving it.

## Stack

- **FastAPI** (Python) — the API
- **Postgres 18**, running locally, database `shootpx` — the database
- **SQLAlchemy** — ORM, models double as the schema definition
- **Firebase Authentication** — identity only. Verifies who someone is
  (Google popup, email-link). Sends zero emails in this project.
- **Resend** — the only thing that sends mail. Our backend's own SMTP relay
  for the magic-link and team-invite emails. Completely separate system from
  Firebase; neither knows the other exists.
- Everything runs local-only right now. No cloud storage (R2/S3/Supabase/etc)
  is wired up yet — deliberately separate, later piece.

## Folder layout (MVC-style)

```
app/
  core/         infra: config, db connection, session-cookie signing,
                Firebase Admin SDK setup, Resend SMTP client
  middleware/   auth.py = the login gate (get_current_user); setup.py =
                CORS registration
  models/       SQLAlchemy tables: user.py, team.py, invite.py
  schemas/      Pydantic request/response shapes (not tables)
  controllers/  the actual logic — routes call these, controllers touch the DB
  routes/       thin FastAPI routers, just URL -> controller wiring
  main.py       creates the app, registers middleware + routers
```

Adding a new feature = one file in each of `models/`, `schemas/`,
`controllers/`, `routes/`, plus two lines in `main.py`.

## Routes that exist right now

| Route | Auth required? | Does |
|---|---|---|
| `GET /health` | no | liveness check |
| `POST /auth/email-link` | no | generates + emails (via Resend) a one-time sign-in link for the given email |
| `POST /auth/session` | no (this IS the login call) | verifies a Firebase ID token, upserts the user, auto-accepts pending invites, sets our session cookie |
| `GET /auth/me` | yes | who am I |
| `POST /auth/logout` | yes | clears the session cookie |
| `POST /teams` | yes | create a team, you become `owner` |
| `GET /teams` | yes | list your teams + your role in each |
| `GET /teams/{id}/members` | yes, must be a member | list the team's roster |
| `GET /teams/{id}/invites` | yes, must be a member | list that team's still-pending invites |
| `POST /teams/{id}/members` | yes, must be `owner` | add someone by email — direct add if they already have an account, otherwise a pending invite + invite email |

## Auth flow

Login is **Google or email magic-link**, both via Firebase — but the two
emails involved (magic-link, team-invite) are sent by **us**, not Firebase:

1. Frontend uses the Firebase JS SDK for the actual login UI — Google popup
   (`signInWithPopup`), or for email: frontend calls our
   `POST /auth/email-link { email, continue_url }`, which asks Firebase
   Admin SDK to *mint* a one-time link (`generate_sign_in_with_email_link`)
   and then emails that link ourselves via Resend (`core/email.py`). We
   don't use Firebase's own `sendSignInLinkToEmail` — its shared sending
   address (`noreply@<project>.firebaseapp.com`) gets flagged as spam.
2. Clicking the link (or completing the Google popup) gets the frontend a
   **Firebase ID token**. It calls `user.getIdToken()` then
   `POST /auth/session { id_token }`.
3. Backend verifies that token via Firebase Admin SDK
   (`core/firebase.py: verify_id_token`) — requires the **service-account
   JSON key** (see Setup below). This is the only place we talk to
   Firebase's verification servers.
4. `controllers/auth_controller.upsert_user_from_firebase` writes/updates a
   `users` row. Primary lookup is by Firebase `uid`; if that's unseen but
   the email already has a row (can happen if Firebase's project doesn't
   auto-link accounts across providers), it falls back to matching by email
   and reuses that row rather than crashing on the `email` unique
   constraint. This was a real bug we hit and fixed — see git history /
   `auth_controller.py` docstring.
5. `team_controller.accept_pending_invites` checks `team_invites` for that
   email and converts any pending ones into real `team_members` rows.
6. Backend sets our own signed session cookie (`session_token`, itsdangerous,
   7 days). From here on, every request just reads that cookie — no
   Firebase call per request.

## Team invites

`POST /teams/{id}/members` (owner-only):
- Email already has a `users` row → added to `team_members` immediately.
- No account yet → a `team_invites` row is created (pending) and an invite
  email goes out via the same Firebase-link + Resend mechanism as login.
  Clicking it both creates their account *and* completes the invite, because
  step 5 above runs on every login regardless of which specific link was
  clicked.

Known, deliberate limitation: if someone has a pending invite under one
email but logs in with a different one, they are correctly **not**
auto-joined (verified) — but nothing tells them that happened. Left as-is
for now; would need invite context threaded through the URL to fix properly,
and there's no real frontend yet to show that message in.

## Schema

Managed by Alembic (`alembic/`) — `alembic upgrade head` applies migrations,
`alembic revision --autogenerate -m "..."` generates one after a model
change. `app/main.py` no longer calls `Base.metadata.create_all()`; it did
until the generation-pipeline work landed a model change (`batch_id`, then
`external_job_id`/`provider` on `GenerationJob`) that `create_all` can't
apply to an already-existing table (it only creates missing tables, never
alters existing ones) — hit twice in one sitting, hence Alembic now instead
of before. `alembic/env.py` imports `app.core.db.engine` directly rather
than building a second connection from `alembic.ini`, so `DATABASE_URL` in
`.env` stays the one place that's actually configured.

**users** — one row per person, id is the Firebase `uid`.
| column | notes |
|---|---|
| id | Firebase uid, PK |
| email | unique |
| name | nullable |
| avatar_url | nullable |
| created_at | |

**teams** — a workspace. id is app-generated (uuid).

**team_members** — join table, many-to-many users<->teams.
| column | notes |
|---|---|
| team_id, user_id | FKs |
| role | `'owner'` \| `'editor'` — plain string, no DB-level enum, no unique constraint on (team_id, user_id) — app code enforces no-duplicates |

**team_invites** — pending invites, keyed by email.
| column | notes |
|---|---|
| team_id, email, role, invited_by | |
| accepted_at | NULL until accepted; app enforces no duplicate pending invite per (team_id, email) |

Roles: only `owner` and `editor`. What each role can actually *do* beyond
"owner can invite people" is intentionally undefined — to be filled in as
real features need permission checks.

## Setup this needs from you (all done as of writing)

1. Firebase project (`pixshoot-18c6b`), Google + Email-link sign-in enabled.
2. `backend/firebase-service-account.json` — gitignored, backend-only.
3. `firebaseConfig` (public) in `test-console/index.html`.
4. Resend: domain `shootpx.com` verified (SPF/DKIM/DMARC), API key in `.env`
   as `SMTP_PASSWORD`.
5. Postgres: local, database `shootpx`, `DATABASE_URL` in `.env`.

## A real gotcha we hit: system clock drift

Windows Time service had never synced (`Local CMOS Clock`, no NTP), causing
intermittent `Token used too early` / `invalid` errors from Firebase's token
verification — even 1 second of drift is enough to fail it. Fixed via
Settings -> Time & Language -> Date & Time -> Sync now. Worth checking first
if login ever starts intermittently failing again with no code changes.

## Testing it locally

Ensure Redis is running first (see the "Running Redis" section in "Core
product system: assets & generation jobs" below for setup). Then, in three
terminals:

```
# terminal 1
cd backend
./venv/Scripts/activate
uvicorn app.main:app --reload

# terminal 2
cd backend
./venv/Scripts/python.exe -m arq app.worker.WorkerSettings

# terminal 3
cd backend/test-console
python -m http.server 5500
```

Open `http://localhost:5500`. Everything's driven by hand from that page —
no real frontend yet. When restarting any server, kill the previous
instance first; leaving old ones running caused real confusion earlier
(multiple processes competing for the same port).

## Core product system: assets & generation jobs

The generic container every one of the 23 tools plugs into. No project
layer — a product decision, not an oversight: the UI flow is strictly
"pick a tool -> generate," so a project-creation step would have added
complexity with no corresponding user-facing value. Assets and jobs are
scoped straight to a team.

**assets** — one row per file, always.
| column | notes |
|---|---|
| id | uuid, PK |
| team_id | FK -> teams.id — who can access it |
| created_by | FK -> users.id — who actually did it. For a generated asset, that's whoever triggered the job, not the AI |
| kind | `'upload'` \| `'generated'` |
| media_type | `'image'` \| `'video'` — inferred from the upload's Content-Type |
| storage_key, url | what `Storage` uses internally / the ready-to-use link |

**generation_jobs** — one row per attempt at running a tool.
| column | notes |
|---|---|
| id | uuid, PK |
| team_id | FK -> teams.id — who can access it |
| created_by | FK -> users.id — who ran it |
| feature_type | plain string — must be a key in the `app/tools/` registry (enforced in `schemas/generation.py`, unknown values are rejected with a 422 before a job is ever created); each tool says which `AIProvider` instance runs it |
| status | `'queued'` \| `'processing'` \| `'done'` \| `'failed'` |
| source_asset_id, output_asset_id | FK -> assets.id, both nullable |
| external_job_id, provider | the aggregator's own job id + which `AIProvider` handled it, both null until submitted — see "Submit/poll, not one blocking call" below |
| input_payload | JSON, empty for now — per-tool options land here later |

**Routes:** `POST /teams/{team_id}/assets` (upload), `POST /generate`
(single), `POST /generate/bulk` (up to 100 assets, one `feature_type`,
shared `batch_id`), `GET /jobs?ids=...`, `GET /batches/{batch_id}`.

Generation is queued, not synchronous: `POST /generate`/`/generate/bulk`
create `GenerationJob` row(s) (`status: "processing"` immediately) and
enqueue arq tasks; a separate worker process (`app/worker.py`, run via
`arq app.worker.WorkerSettings`) does the actual generation later. Two
concurrency limits apply, independently:
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

**Submit/poll, not one blocking call.** `AIProvider` (`core/ai_provider.py`)
is deliberately *not* "call it and get bytes back" — real aggregators (fal.ai,
Segmind, ...) are themselves async: you submit and get an external job id
back in ~1s, and the actual generation (seconds to minutes, more for video)
happens on their side. `submit()` does the minimum to get that id;
`poll_result()` is one status check, raising `GenerationPending` if it's not
done yet. `app/worker.py`'s `run_generation_job` never blocks waiting on
either — one arq invocation does exactly one submit or one poll, and if
still pending, requeues itself via `Retry(defer=GENERATION_POLL_INTERVAL_SECONDS)`,
freeing its worker slot in the meantime (same trick as the lock-wait retry).
This means a single job's lifetime can span many separate invocations,
possibly on different worker processes once more than one is running —
nothing about progress lives in memory; `external_job_id`/`provider` on the
row and the Redis lock (refreshed across those invocations, not re-acquired
per invocation — `run_generation_job` checks whether it already holds the
key before attempting `SET NX`) are the only state. `GENERATION_TIMEOUT_SECONDS`
bounds a job's total wall-clock lifetime independent of arq's own
`job_timeout` (which only bounds a single submit/poll HTTP call).

`MockAIProvider` simulates this by encoding a "ready at" timestamp into its
own `external_job_id` rather than sleeping inline (`MOCK_GENERATION_DELAY_SECONDS`,
default 3s) — instant mock results would make the per-team lock
unobservable by polling, and a sleep would put it back to blocking a
worker slot, defeating the whole point. Swapping in a real provider means
implementing `submit()`/`poll_result()` against that provider's actual API;
nothing in `worker.py` changes.

**Tool registry (`app/tools/`).** A job's `feature_type` doesn't call
`AIProvider` directly — `app/worker.py` looks it up in the shared registry
(`app/tools/registry.py`'s `TOOLS` dict) first, and calls whichever
`ToolSpec.provider` that entry names. One file per tool
(`app/tools/on_model_shots.py`, `app/tools/ugc.py`, ...), each registering
its own `ToolSpec` (`feature_type`, `display_name`, `output_media_type`,
`provider`) at import time — `app/tools/__init__.py` imports every tool
module so this happens once, at startup. This is the actual seam for "23
tools, each maybe a different aggregator": adding a tool is one new file
in `app/tools/`, imported from `__init__.py` — not a change to
`worker.py`, `registry.py`, `generation_controller.py`, or the schemas.
`app/tools/_template.py` is a copy-paste starting point for that one new
file (leading `_` so it's never itself auto-imported/registered) — the
mechanical steps are literally copy it, fill in four fields, add one
import line, done.
Once a tool has real per-provider request/response logic (mapping generic
`input_payload` to that provider's actual request shape, and its response
back to `GenerationResult`), that logic lives in that tool's own file too
— nothing shared gets more crowded as more tools are added. Every tool
today points at the same `MockAIProvider` — there's no real provider
adapter yet — but two tools (`on_model_shots`, `ugc`) are registered and
dispatch through the registry for real, proven against a live server
(`scripts/test_pipeline.py` plus a one-off HTTP check that an
unregistered `feature_type` gets a 422 and `ugc` runs end to end).
`register()` (`registry.py`) raises loudly on a duplicate `feature_type`
at import time, rather than letting two tools silently fight over one
dispatch key. `output_media_type` isn't cross-checked against what the
provider actually returns yet (there's only ever been one mock result
shape to check against) — worth adding once a video-capable provider
exists, so a misconfigured tool fails loudly instead of quietly
mislabeling an asset.

**Running Redis:** on a machine with Docker, the simplest option is
`docker run -d --name shootpx-redis -p 6379:6379 --restart unless-stopped
redis:7-alpine` — `REDIS_URL=redis://localhost:6379/0`. Without Docker/WSL,
**Memurai** is the native-Windows-service alternative (Redis-protocol-compatible,
`winget install Memurai.MemuraiDeveloper` or the MSI from
[memurai.com](https://www.memurai.com/)), also on `127.0.0.1:6379` by
default. Either way it needs to be running before the worker/API start —
neither starts it for you.

**Abstractions**, same pattern as auth/email — one interface, one local
implementation, swap later without touching callers:
- `core/storage.py` — `Storage` interface, `LocalStorage` writes to
  `STORAGE_ROOT_DIR`, served back at `/files/...` via `StaticFiles`. Swap
  for R2/S3 later.
- `core/ai_provider.py` — `AIProvider` interface (`submit`/`poll_result`),
  `MockAIProvider` returns a real tiny PNG after a simulated delay, proving
  the request -> job -> asset loop without any real AI call or per-tool
  logic.

**Permissions:** `core/permissions.py`'s `compute_permissions(role)` gates
these — `can_upload_assets` and `can_generate`, both true for owner and
editor today. Never a hardcoded `role == "owner"` check outside that one
file; `can_manage_team` (owner-only) is the one exception.

## Product imports — scraping a product URL into real assets

**`product-scrapper`** (sibling repo, `../product-scrapper`) turns a
product page URL into name/description/brand/price/theme colors and a
list of image URLs — its own `extract_product()` (`extractor.py`),
already independently tested (25 offline tests). It's a Python library,
not a service, and its call blocks for 2-25s (sometimes launching a real
headless Chromium) — the exact shape `AIProvider` was built to avoid
calling directly, so it doesn't get imported into this backend. Instead:

- **`product-scrapper/service.py`** — a small FastAPI wrapper added
  specifically for this integration, giving `extract_product()` the same
  submit/poll HTTP shape as `AIProvider`: `POST /extract {url}` returns a
  job id immediately (runs the actual scrape on a bounded thread pool,
  `MAX_CONCURRENT_SCRAPES`, so concurrent requests don't launch unbounded
  Chromium instances), `GET /extract/{id}` polls `{status, result}`. Run
  separately: `uvicorn service:app --port 8501` (after `pip install -r
  requirements.txt && playwright install chromium` in that repo).
- **`core/product_scraper_client.py`** (this repo) — thin `submit()`/
  `poll()` client for that service, same pattern as `AIProvider`, but
  *not* an `AIProvider` itself: a product import's output (several images
  + structured data) doesn't fit `GenerationResult`'s one-image shape.
- **`ProductImport`** (`models/product_import.py`) — its own table, not
  bolted onto `GenerationJob`: `status`, `external_job_id` (the scraper
  service's own job id), promoted fields (`product_name`, `price`, ...),
  and `raw_result` (the scraper's full result, verbatim, nothing lost even
  though only some fields get their own column).
- **`app/worker.py`'s `run_product_import`** — identical submit/poll/Retry
  shape to `run_generation_job`, against `ProductImport` instead of
  `GenerationJob` and `product_scraper_client` instead of `AIProvider`.
  No per-team lock (nothing about scraping needs one team's imports
  serialized) — shares the same global `max_jobs` pool as generation for
  now, not a dedicated cap; splitting them is a reasonable thing to do
  once real traffic shows it's needed. Once the scrape itself succeeds,
  each of its (up to `MAX_IMPORTED_IMAGES`, currently 20) image URLs gets
  downloaded and saved as a real `Asset` (`kind="imported"`,
  `product_import_id` set) via the same `Storage` abstraction generation
  output already goes through — so a scraped image is immediately usable
  as `source_asset_id` for `/generate`, same as an upload.
- **Routes:** `POST /product-imports` (`team_id`, `url`), `GET
  /product-imports/{id}` — same "create it, poll it" shape as generation,
  gated on `can_upload_assets` (a scraped image is conceptually an upload,
  not a generation).

A scrape that doesn't reach `status: "ok"` (blocked, not_a_product,
unreachable, ...) marks the `ProductImport` failed with the scraper's own
message — verified end to end with a real unreachable-domain URL through
the full stack (API -> queue -> worker -> scraper client -> wrapper
service -> `extract_product()` -> back), and the success path (metadata +
image download + `Asset` creation) verified by feeding `_poll_import` a
synthetic successful result pointing at a real HTTP URL, since asserting
against a live third-party product page in a test isn't stable.

## Caching — `core/cache.py`

A generic namespaced read-through cache on the same Redis instance
already backing the arq queue and per-team lock. A namespace is just a
key prefix (`cache:<namespace>:<key>`), so one can be cleared
(`clear_namespace()`, SCAN-based, doesn't block Redis) without touching
another's data — that's the entire reason it's not one flat cache. Adding
a namespace later (a feed cache, say, whenever a feed feature actually
exists) needs nothing here; a caller just starts passing a new namespace
string. Sync client, matching the rest of this codebase's sync DB layer.

Two namespaces wired in today:
- **`login`** (`middleware/auth.py`) — caches the `User` row
  `get_current_user` otherwise fetches on *every* authenticated request.
  `LOGIN_CACHE_TTL_SECONDS` (60s) bounds staleness for anything the TTL
  alone would need to catch; the one write path that can actually change
  a cached field (`auth_controller.upsert_user_from_firebase`, on
  sign-in) invalidates immediately rather than waiting it out.
- **`media`** (`core/asset_lookup.py`) — caches `Asset` row lookups.
  `GET /jobs`/`GET /batches/{id}` get polled repeatedly while a job runs,
  re-resolving the same source/output asset ids every poll.
  `MEDIA_CACHE_TTL_SECONDS` (300s, longer than login's) needs no
  write-path invalidation: assets are effectively immutable once created
  (no update/delete endpoint exists anywhere in this app). `get_assets_cached()`
  stays batch-aware on a miss — checks the cache per id, then one `IN (...)`
  query for whatever's missing, never N individual queries.

Cached values are plain JSON dicts, not ORM instances, converted on both
sides of the cache (`_to_cache`/`_from_cache` in each caller) — a cached
SQLAlchemy instance would be detached from any `Session`, and
`Model(**dict)` only stays safe to read from as long as nothing touches a
relationship on it (documented at each call site; every current caller
only reads plain columns, never `.memberships` or similar).

Verified with a poison test for each namespace, not just "the code looks
right": populate the cache, overwrite the cached value directly in Redis
to something the database does *not* have (a fake email/name, a fake
asset URL), confirm the API actually returns the poisoned value (proving
it's genuinely being read from cache, not silently bypassed), then
`cache.delete()`/invalidate and confirm the real value comes back. Also
verified `clear_namespace('login')` deletes only that namespace's keys,
leaving `media`'s untouched.

## Explicitly out of scope for now

- File/media storage (R2, S3, Supabase, etc.)
- What owners vs editors can actually do beyond team membership itself
- Billing/subscriptions
- Proactive "you were invited under a different email" messaging
- Real frontend integration (only the test console exists)
