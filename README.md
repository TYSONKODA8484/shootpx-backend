# ShootPX Backend

FastAPI backend for ShootPX — auth, teams/workspaces, and the core
asset/generation-job system that every AI tool plugs into.

- **Auth**: Google sign-in or a passwordless email link, both via Firebase
  Authentication. Firebase only verifies identity — it never sends mail;
  the magic-link and team-invite emails are sent by this backend itself,
  through Resend.
- **Teams**: multi-tenant workspaces. One person can belong to many teams,
  each with a role (`owner` / `editor`). Inviting someone who doesn't have
  an account yet works — they get an email, and joining happens
  automatically the moment they first sign in.
- **Assets & generation jobs**: the generic container every tool works
  through. Upload a file, `POST /generate` with a `feature_type`, get back
  a job with an output asset. No per-tool logic yet — a mock AI provider
  proves the request → job → asset loop end to end.

See [`DESIGN.md`](./DESIGN.md) for the full architecture writeup — schema,
auth flow, and the reasoning behind the bigger decisions. This file is just
setup and day-to-day usage.

## Stack

Python / FastAPI · PostgreSQL · SQLAlchemy · Firebase Authentication ·
Resend (SMTP) · local disk storage (swappable later for R2/S3)

## Project layout

```
app/
  core/         config, DB connection, session-cookie signing,
                Firebase Admin SDK, storage + AI-provider abstractions
  middleware/   the login gate (get_current_user), CORS setup
  models/       SQLAlchemy tables
  schemas/      Pydantic request/response shapes
  controllers/  the actual logic — routes call these
  routes/       thin FastAPI routers, just URL -> controller wiring
  main.py       creates the app, registers everything
test-console/   a bare-bones HTML page for exercising the API by hand
                (no real frontend exists yet)
```

## Setup

**1. Clone and create a virtualenv**
```bash
git clone <repo-url>
cd backend
python -m venv venv
./venv/Scripts/activate        # Windows
# source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
```

**2. Postgres**

Create a local database called `shootpx`. Tables are created automatically
from the SQLAlchemy models on first run — no migrations to run.

**3. Environment variables**

Copy the template and fill in real values:
```bash
cp .env.example .env
```
| Variable | Where it comes from |
|---|---|
| `DATABASE_URL` | your local Postgres connection string |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | Firebase Console → Project Settings → Service Accounts → *Generate new private key*. Save the downloaded JSON as `backend/firebase-service-account.json` (gitignored) |
| `SMTP_*` | [Resend](https://resend.com) → API Keys → *Create API Key*. `SMTP_PASSWORD` is the `re_...` key |

**4. Firebase sign-in methods**

In Firebase Console → Authentication → Sign-in method, enable **Google**
and **Email link (passwordless)**.

## Running it

```bash
uvicorn app.main:app --reload
```

The API is now at `http://localhost:8000`, with interactive docs (every
route, "Try it out" buttons, even a file picker for uploads) at
**`http://localhost:8000/docs`** — this is the easiest way to explore or
test any endpoint by hand.

For login flows specifically (Google popup, magic-link), FastAPI's docs
page can't drive Firebase's client SDK, so use the test console instead:
```bash
cd test-console
python -m http.server 5500
```
Open `http://localhost:5500`, sign in there, then open `/docs` **in the
same browser** — your session cookie carries over automatically since both
are served from `localhost`.

> Only run one instance of each server at a time — leaving old ones running
> in the background causes real, confusing bugs (two processes fighting
> over the same port). Kill the previous one before restarting.

## API overview

| | |
|---|---|
| `POST /auth/session` | exchange a Firebase ID token for our session cookie |
| `POST /auth/email-link` | request a magic sign-in link by email |
| `GET /auth/me` / `POST /auth/logout` | |
| `POST /teams` / `GET /teams` | create / list your teams |
| `POST /teams/{id}/members` | invite someone by email (owner-only) |
| `GET /teams/{id}/members` / `GET /teams/{id}/invites` | |
| `POST /teams/{id}/assets` | upload a file |
| `POST /generate` | run a tool: `team_id`, `feature_type`, `source_asset_id`, `input_payload` |

Full request/response shapes are in `/docs`, not duplicated here — this
table is just so you know what exists before opening it.

## Testing

There's no automated test suite yet — testing has been done by hand
against a live database via `/docs` and the test console, verifying actual
database state and actual file bytes, not just HTTP status codes. See
`DESIGN.md` for the reasoning behind specific design decisions if a test
result looks surprising.
