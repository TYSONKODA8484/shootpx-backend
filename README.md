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
  through. Upload a file, `POST /generate` (or `/generate/bulk`) with a
  `feature_type` — the job is queued and processed by a separate worker;
  poll `GET /jobs` or `GET /batches/{batch_id}` for status. No per-tool
  logic yet — a mock AI provider proves the request → job → asset loop end
  to end.

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
                Firebase Admin SDK, storage + AI-provider abstractions,
                product-scrapper client
  tools/        the feature_type registry — one file per tool (see
                DESIGN.md's "Tool registry" section)
  middleware/   the login gate (get_current_user), CORS setup
  models/       SQLAlchemy tables
  schemas/      Pydantic request/response shapes
  controllers/  the actual logic — routes call these
  routes/       thin FastAPI routers, just URL -> controller wiring
  worker.py     arq worker process — runs queued generation jobs
  main.py       creates the app, registers everything
alembic/        DB migrations (alembic upgrade head / alembic revision --autogenerate)
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

Create a local database called `shootpx`, then apply migrations:
```bash
alembic upgrade head
```
Schema is managed by Alembic — models alone don't create/alter tables
anymore. After changing a model in `app/models/`, generate a migration and
apply it:
```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```
Always read the generated file in `alembic/versions/` before running
`upgrade` — autogenerate is a diff, not a guarantee; it can miss things
(e.g. renames look like a drop + add) or include things you didn't intend.

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
| `REDIS_URL` | your local Redis — see `DESIGN.md` for how to get one running on Windows |
| `PRODUCT_SCRAPER_URL` | where the `product-scrapper` service is running (see step 5) — only needed for `/product-imports` |

**4. Firebase sign-in methods**

In Firebase Console → Authentication → Sign-in method, enable **Google**
and **Email link (passwordless)**.

**5. product-scrapper (optional — only for `/product-imports`)**

Separate repo (`../product-scrapper`), separate process. From that repo:
```bash
pip install -r requirements.txt
playwright install chromium
uvicorn service:app --port 8501
```
See `DESIGN.md`'s "Product imports" section for why it's a separate
service rather than imported into this backend.

## Running it

This now needs **two processes** — the API and the arq worker that
actually runs generation jobs *and* product imports. Start Redis first
(see `DESIGN.md` for how to get one running locally on Windows), then:

```bash
# terminal 1 — the API
uvicorn app.main:app --reload

# terminal 2 — the worker (processes queued /generate, /generate/bulk, and /product-imports jobs)
./venv/Scripts/python.exe -m arq app.worker.WorkerSettings
```

`/product-imports` additionally needs the product-scrapper service (step
5 above) running — everything else works without it.

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
| `POST /generate` | run a tool on one asset: `team_id`, `feature_type`, `source_asset_id`, `input_payload` — enqueued, returns immediately |
| `POST /generate/bulk` | run a tool on up to 100 assets at once: `team_id`, `feature_type`, `asset_ids`, `input_payload` — returns a `batch_id` + all job ids immediately |
| `GET /jobs?ids=...` | poll one or many jobs by comma-separated id |
| `GET /batches/{batch_id}` | poll a bulk submission's aggregate + per-job status |
| `POST /product-imports` | scrape a product URL: `team_id`, `url` — enqueued, returns immediately |
| `GET /product-imports/{id}` | poll status; once done, includes name/description/brand/price/theme colors + every scraped image as a real asset |

Full request/response shapes are in `/docs`, not duplicated here — this
table is just so you know what exists before opening it.

## Testing

There's no automated test suite yet — testing has been done by hand
against a live database via `/docs` and the test console, verifying actual
database state and actual file bytes, not just HTTP status codes. See
`DESIGN.md` for the reasoning behind specific design decisions if a test
result looks surprising.
