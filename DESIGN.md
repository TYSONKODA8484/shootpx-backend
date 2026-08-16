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

```
# terminal 1
cd backend
./venv/Scripts/activate
uvicorn app.main:app --reload

# terminal 2
cd backend/test-console
python -m http.server 5500
```

Open `http://localhost:5500`. Everything's driven by hand from that page —
no real frontend yet. When restarting either server, kill the previous
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
| feature_type | plain string — the future dispatch key for which of the 23 tools' logic runs; today every value hits the same `MockAIProvider` |
| status | `'queued'` \| `'processing'` \| `'done'` \| `'failed'` |
| source_asset_id, output_asset_id | FK -> assets.id, both nullable |
| input_payload | JSON, empty for now — per-tool options land here later |

**Routes:** `POST /teams/{team_id}/assets` (upload), `POST /generate` (body:
`team_id`, `feature_type`, `source_asset_id`, `input_payload`) — synchronous
today (no queue/worker), calls the AI provider inline and returns the
finished job.

**Abstractions**, same pattern as auth/email — one interface, one local
implementation, swap later without touching callers:
- `core/storage.py` — `Storage` interface, `LocalStorage` writes to
  `STORAGE_ROOT_DIR`, served back at `/files/...` via `StaticFiles`. Swap
  for R2/S3 later.
- `core/ai_provider.py` — `AIProvider` interface, `MockAIProvider` returns
  a real tiny PNG instantly, proving the request -> job -> asset loop
  without any real AI call or per-tool logic.

**Permissions:** `core/permissions.py`'s `compute_permissions(role)` gates
these — `can_upload_assets` and `can_generate`, both true for owner and
editor today. Never a hardcoded `role == "owner"` check outside that one
file; `can_manage_team` (owner-only) is the one exception.

## Explicitly out of scope for now

- File/media storage (R2, S3, Supabase, etc.)
- What owners vs editors can actually do beyond team membership itself
- Billing/subscriptions
- Proactive "you were invited under a different email" messaging
- Real frontend integration (only the test console exists)
