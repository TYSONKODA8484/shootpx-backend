# The ShootPX Backend Book

**A complete, beginner-friendly guide to every piece of this codebase — what it
is, why it exists, how it works, what it replaced, and what comes next.**

---

## How to read this book

This is not a README and not an API reference. It is a **narrative**. It starts
at the very beginning — an empty folder — and walks forward through every
decision, in the order those decisions were actually made, until it reaches the
code that is running today. Then it looks forward at what hasn't been built yet.

You should be able to read this front to back knowing nothing about the project
and come out the other side able to change the code safely.

**Three ways to use it:**

| If you are… | Read… |
|---|---|
| Brand new to this codebase | Parts I → II → III, in order, cover to cover |
| Looking for one specific thing | The Table of Contents, then jump |
| Trying to understand *why* something is weird | Part V (The Deprecation Ledger) — the weirdness is almost always a scar from something that used to be different |

---

## 📜 The Append-Only Rule

**This book is never edited destructively. It only ever grows.**

When something in the codebase changes, we do **not** delete the old
explanation. We mark it, explain why it changed, and write the new version
underneath it. That way this file is a complete history at the code level —
you can always answer "why on earth is it like this?" because the answer is
still here, three paragraphs up.

The rules, concretely:

1. **Never delete a section.** Ever. Even if the code it describes is gone.
2. **Mark it instead.** Change its status badge to 🔴 and add a
   `> **Why it went away:**` note directly underneath.
3. **Write the replacement below it**, as a new sub-section, marked 🟢.
4. **Add a row to the Deprecation Ledger** (Part V) pointing at both.
5. **Add a dated entry to the Timeline** (Part IV).
6. When you add a genuinely new feature, add a new chapter to Part III and a
   Timeline entry. Nothing else needs to move.

There is a step-by-step template for doing all six at the bottom of this book:
see **[Appendix D: How to Append to This Book](#appendix-d-how-to-append-to-this-book)**.

---

## 🎨 The Status Legend

Every section, table row, and ledger entry in this book carries one of these:

| Badge | Meaning |
|---|---|
| 🟢 **CURRENT** | This is live in the code right now. Trust it. |
| 🟡 **CHANGED** | Still exists, but works differently than when it was first written. The original description is kept above the new one. |
| 🔴 **DEPRECATED / REMOVED** | Gone from the code. Kept here purely as history so you understand what came before. **Do not write new code against anything marked 🔴.** |
| ⚪ **ORPHANED** | Still physically in the code, but nothing calls it. Not wrong — just unused. A cleanup candidate. |
| 🔵 **PLANNED** | Deliberately not built yet. Documented so nobody re-derives the decision. |

> 🔴 sections are rendered in blockquotes with a "Why it went away" note.
> If you are reading this on GitHub, GitHub strips inline colours — the badge
> emoji is the colour. That is deliberate: it renders identically everywhere.

---

## Table of Contents

**[Part I — The Ground Floor](#part-i--the-ground-floor)**
- [1. What ShootPX Is](#1-what-shootpx-is)
- [2. The One-Paragraph Mental Model](#2-the-one-paragraph-mental-model)
- [3. The Stack, and Why Each Piece](#3-the-stack-and-why-each-piece)
- [4. Running It On Your Machine](#4-running-it-on-your-machine)

**[Part II — The Shape of the Code](#part-ii--the-shape-of-the-code)**
- [5. The Seven Layers](#5-the-seven-layers)
- [6. The Life of a Request](#6-the-life-of-a-request)
- [7. The Two Processes](#7-the-two-processes)
- [8. The Swappable-Seam Pattern](#8-the-swappable-seam-pattern)

**[Part III — The Chapters](#part-iii--the-chapters)**
- [Chapter 1 — Configuration](#chapter-1--configuration)
- [Chapter 2 — The Database Layer](#chapter-2--the-database-layer)
- [Chapter 3 — The Data Model](#chapter-3--the-data-model)
- [Chapter 4 — Identity and Login](#chapter-4--identity-and-login)
- [Chapter 5 — Sessions and the Auth Gate](#chapter-5--sessions-and-the-auth-gate)
- [Chapter 6 — Teams, Invites and Permissions](#chapter-6--teams-invites-and-permissions)
- [Chapter 7 — Assets and Storage](#chapter-7--assets-and-storage)
- [Chapter 8 — Generation Jobs](#chapter-8--generation-jobs)
- [Chapter 9 — The Queue and the Worker](#chapter-9--the-queue-and-the-worker)
- [Chapter 10 — Bulk Generation and Status Polling](#chapter-10--bulk-generation-and-status-polling)
- [Chapter 11 — The AI Provider](#chapter-11--the-ai-provider)
- [Chapter 12 — The Tool Registry](#chapter-12--the-tool-registry)
- [Chapter 13 — Database Migrations](#chapter-13--database-migrations)
- [Chapter 14 — Product Imports](#chapter-14--product-imports)
- [Chapter 15 — Caching](#chapter-15--caching)
- [Chapter 16 — Testing and the Test Console](#chapter-16--testing-and-the-test-console)

**[Part IV — The Timeline](#part-iv--the-timeline)**

**[Part V — The Deprecation Ledger](#part-v--the-deprecation-ledger)**

**[Part VI — What Comes Next](#part-vi--what-comes-next)**

**[Part VII — Appendices](#part-vii--appendices)**
- [Appendix A: Complete File Map](#appendix-a-complete-file-map)
- [Appendix B: Every Route](#appendix-b-every-route)
- [Appendix C: Glossary](#appendix-c-glossary)
- [Appendix D: How to Append to This Book](#appendix-d-how-to-append-to-this-book)
- [Appendix E: Known Documentation Drift](#appendix-e-known-documentation-drift)

---
---

# Part I — The Ground Floor

## 1. What ShootPX Is

ShootPX is a product-photography platform. The pitch: a business uploads a photo
of their product, picks one of (eventually) **23 AI tools** — "put this on a
model", "make a UGC-style video", "generate a photoshoot" — and gets a new
image or video back.

**This repository is the backend only.** There is no real frontend yet. What
exists is:

- an HTTP API (FastAPI),
- a background worker that does the slow work,
- and a deliberately ugly HTML page (`test-console/`) used to click through the
  API by hand until a real frontend exists.

The critical thing to understand about the current state: **none of the 23 AI
tools are real yet.** Every tool routes to a `MockAIProvider` that returns a
1×1 transparent PNG. That is not a gap — it is the *point*. All the hard,
boring, easy-to-get-wrong machinery around the AI (queuing, concurrency limits,
per-team fairness, status polling, retries, timeouts, storage, permissions) is
built and proven end to end. When a real AI provider gets plugged in, it slots
into one clearly-marked seam and nothing else changes.

> **Beginner note:** if you have only ever built simple CRUD apps, the
> surprising thing about this codebase will be how much of it is about *waiting*
> — waiting for a slow AI, without blocking anything. Chapters 9 and 11 are
> where that lives, and they are the heart of the project.

---

## 2. The One-Paragraph Mental Model

> A **user** signs in with Google or a magic email link. They belong to one or
> more **teams**. Inside a team they upload **assets** (files). They then create
> a **generation job**: "run tool X on asset Y". That job is *not* run
> immediately — it is put on a **queue**. A separate **worker** process picks it
> up, grabs a **per-team lock** so that one team can't hog everything, submits
> the work to an **AI provider**, and then polls that provider until it's done.
> When it's done, the result is saved as a brand-new **asset**, and the job row
> is marked `done`. The user finds out by **polling** `GET /jobs`.

Everything else in this codebase is a variation on, or a support system for,
that one paragraph.

---

## 3. The Stack, and Why Each Piece

| Piece | What it does here | Why this one |
|---|---|---|
| **Python + FastAPI** | The HTTP API | Async-capable, automatic `/docs` UI, Pydantic validation built in |
| **PostgreSQL** | The database (local, db name `shootpx`) | Relational data with real foreign keys; JSON columns where we need flexibility |
| **SQLAlchemy** | ORM — Python classes ↔ database tables | Models become the single source of truth for schema |
| **Alembic** | Database migrations | See [Chapter 13](#chapter-13--database-migrations) — replaced a simpler approach that broke |
| **Redis** | Three separate jobs: the task queue, the per-team lock, and the cache | Already needed for the queue, so the lock and cache ride along for free |
| **arq** | The task queue library on top of Redis | Small, async-native, has the `Retry` primitive this design leans on heavily |
| **Firebase Authentication** | Proves *who someone is*. Nothing else. | Handles Google OAuth and magic-link token minting so we never touch passwords |
| **Resend** | Sends our emails (SMTP relay) | Firebase's own sending address gets flagged as spam — see [Chapter 4](#chapter-4--identity-and-login) |
| **itsdangerous** | Signs our own session cookie | Simpler than JWT; we don't need cross-service portability |
| **httpx** | Outbound HTTP (product scraper, image downloads) | Modern, supports timeouts and redirects cleanly |
| **Local disk** | Where uploaded and generated files live | Deliberately temporary — see [Chapter 7](#chapter-7--assets-and-storage) |

**Two things are notably absent, on purpose:**

- 🔵 **No cloud storage (S3/R2).** Files are on local disk behind a swappable
  interface. Swapping is a one-file change.
- 🔵 **No automated test suite.** Verification has been done by hand and via one
  end-to-end script against a live database. See [Chapter 16](#chapter-16--testing-and-the-test-console).

---

## 4. Running It On Your Machine

You need **four things running**, in this order:

```bash
# 0. Redis must already be up.
#    Docker:  docker run -d --name shootpx-redis -p 6379:6379 --restart unless-stopped redis:7-alpine
#    Windows without Docker: Memurai (winget install Memurai.MemuraiDeveloper)

# 0b. Postgres must be up, with a database called `shootpx`.
alembic upgrade head       # creates/updates the schema — the app will NOT do this for you

# 1. The API
uvicorn app.main:app --reload

# 2. The worker (a SEPARATE terminal — nothing generates without this)
./venv/Scripts/python.exe -m arq app.worker.WorkerSettings

# 3. The test console (a THIRD terminal, only if you want the click-through UI)
cd test-console && python -m http.server 5500
```

Optional, and only for `/product-imports`:

```bash
# 4. The product-scrapper service — a SEPARATE REPO at ../product-scrapper
uvicorn service:app --port 8501
```

**Where to click:**
- `http://localhost:8000/docs` — FastAPI's auto-generated interactive docs. Every
  route, "Try it out" buttons, even a file picker for uploads. This is the best
  way to explore the API.
- `http://localhost:5500` — the test console. Needed for login flows specifically,
  because `/docs` can't drive Firebase's browser SDK. Sign in there, then open
  `/docs` **in the same browser** — the session cookie carries over.

> ⚠️ **A real gotcha, learned the hard way:** only run *one* instance of each
> server. Leaving an old `uvicorn` or worker running in the background causes
> genuinely confusing bugs — two processes fighting over one port, or an old
> worker running stale code. Kill the previous one before restarting.

> ⚠️ **Another real one:** if login starts failing intermittently with
> "Token used too early" and you changed nothing, **check your system clock**.
> Windows Time service had never synced on the dev machine, and even 1 second of
> drift makes Firebase reject tokens. Settings → Time & Language → Sync now.

---
---

# Part II — The Shape of the Code

## 5. The Seven Layers

The `app/` folder is MVC-ish, with a strict rule: **each layer only talks to the
one below it.**

```
   HTTP request
        │
        ▼
┌───────────────────┐
│  routes/          │  URL → function. Nothing else. No logic, ever.
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  middleware/      │  The auth gate (get_current_user) + CORS.
└───────────────────┘  Runs BEFORE the route body.
        │
        ▼
┌───────────────────┐
│  schemas/         │  Pydantic. Validates the request shape,
└───────────────────┘  defines the response shape. Rejects bad input
        │              with a 422 before your code ever runs.
        ▼
┌───────────────────┐
│  controllers/     │  THE ACTUAL LOGIC. Permissions, DB writes,
└───────────────────┘  business rules. This is where you read first.
        │
        ▼
┌───────────────────┐
│  models/          │  SQLAlchemy tables. One class = one table.
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  core/            │  Infrastructure: config, DB engine, Redis,
└───────────────────┘  storage, AI provider, Firebase, email, cache.
        │              Swappable seams live here.
        ▼
┌───────────────────┐
│  tools/           │  The 23-tools registry. One file per tool.
└───────────────────┘
```

Plus one thing outside the stack entirely:

```
┌───────────────────┐
│  worker.py        │  A SEPARATE PROCESS. Reads the queue, does the
└───────────────────┘  slow work. Talks to models/ and core/ directly.
```

**The payoff of this layout:** adding a normal feature means one new file in
each of `models/`, `schemas/`, `controllers/`, `routes/`, plus two lines in
`main.py`. Adding a *tool* means one file in `tools/` and one import line —
nothing else at all.

---

## 6. The Life of a Request

Let's trace `POST /generate` all the way through. This single path touches
almost every layer, so if you understand it you understand the codebase.

```
1.  Browser sends: POST /generate
    Cookie: session_token=<signed blob>
    Body:   { team_id, feature_type, source_asset_id, input_payload }
                    │
                    ▼
2.  middleware/setup.py  — CORS check. Is this origin allowed?
                    │
                    ▼
3.  routes/generation_routes.py — matches the URL, sees two Depends():
                                  get_db and get_current_user.
                    │
                    ▼
4.  middleware/auth.py: get_current_user()
      a. Read the `session_token` cookie.
      b. core/security.py: read_session_token() — verify the signature and
         that it hasn't expired. Get back a user_id. (Bad/missing → 401.)
      c. Check the Redis "login" cache for that user_id.  ← Chapter 15
      d. On a miss: db.get(User, user_id), then populate the cache.
                    │
                    ▼
5.  schemas/generation.py: GenerateRequest
      Pydantic validates the body. The feature_type validator checks the
      value against the tool registry — an unknown tool is rejected with
      a 422 HERE, before any row is ever created.   ← Chapter 12
                    │
                    ▼
6.  controllers/generation_controller.py: run_generation()
      a. core/permissions.py: get_membership() — are you on this team?
         Not a member → 404 (not 403; we don't confirm the team exists).
      b. compute_permissions(role).can_generate — are you allowed?
      c. If a source_asset_id was given: does it belong to THIS team?
      d. INSERT a GenerationJob row with status="processing".
      e. core/queue.py: enqueue_generation_job() — hand it to arq. Return.
         (If the enqueue itself throws, mark the job failed honestly
          rather than leaving it stuck at "processing" forever.)
                    │
                    ▼
7.  Response: 201 Created, the job row. TOTAL TIME: milliseconds.
    Nothing has been generated. That's correct.

    ─────────── meanwhile, in the OTHER process ───────────

8.  worker.py: run_generation_job(job_id, team_id)   ← Chapters 9 & 11
      a. Try to take the per-team Redis lock.
         Held by another job? → raise Retry(0.5s) and give up the slot.
      b. Not yet submitted (external_job_id is NULL)?
           → look up the tool in the registry
           → tool.provider.submit(...) → get an external job id back
           → save external_job_id + provider on the row
           → raise Retry(3s). Give up the slot.
      c. Already submitted?
           → tool.provider.poll_result(handle)
           → GenerationPending?  raise Retry(3s). Give up the slot.
           → Done? Save the bytes via core/storage.py, create a NEW
             Asset row, point job.output_asset_id at it, status="done".
           → Release the lock.
                    │
                    ▼
9.  Browser polls GET /jobs?ids=<job_id> every second or so until
    status flips to "done", then reads output.url.   ← Chapter 10
```

**The single most important idea on that diagram** is in step 8: the worker
*never blocks*. Every branch either finishes the job or throws `Retry` and hands
its worker slot back. A job that takes four minutes of AI time occupies a worker
for maybe 200 milliseconds total, spread across ~80 separate invocations.

---

## 7. The Two Processes

This trips up newcomers constantly, so it gets its own section.

|  | **API process** (`uvicorn app.main:app`) | **Worker process** (`arq app.worker.WorkerSettings`) |
|---|---|---|
| Entry point | `app/main.py` | `app/worker.py` |
| Handles | HTTP requests | Queued tasks |
| Talks to | Postgres, Redis (enqueue + cache), Firebase, SMTP | Postgres, Redis (queue + lock), AI provider, scraper service |
| If it's down | Nothing works at all | Requests still succeed — but every job sits at `"processing"` forever |
| Shares memory with the other? | **No. Never.** | **No. Never.** |

**"Shares no memory" is a hard constraint, not a detail.** It is why
`GenerationJob` has `external_job_id` and `provider` columns: the worker
invocation that *submits* a job may be a completely different process from the
one that later *polls* it. Anything one invocation needs to tell the next must
be written to the database row or to Redis. Nothing may live in a Python
variable between invocations.

Both processes independently import every model module (see `app/main.py` lines
8–19 and `app/worker.py` lines 80–84). This looks like pointless boilerplate and
is not: SQLAlchemy resolves `relationship("TeamInvite")` by *string name*
against whatever classes are registered in *this* process. Miss one import and
the very first ORM query in that process explodes with
`InvalidRequestError`. This was a real production-stopping bug — see
[the Timeline, 2026-08-17, commit `0778f81`](#part-iv--the-timeline).

---

## 8. The Swappable-Seam Pattern

The same pattern appears five times in `core/`. Learn it once, recognise it
everywhere:

```python
# 1. An abstract interface describing WHAT, never HOW.
class Storage(ABC):
    @abstractmethod
    def save(self, key: str, content: bytes) -> None: ...
    @abstractmethod
    def url_for(self, key: str) -> str: ...

# 2. One concrete implementation for right now.
class LocalStorage(Storage):
    ...

# 3. ONE module-level instance. Every caller in the app goes through this
#    single line and never names the concrete class.
storage: Storage = LocalStorage(...)
```

Swapping local disk for Cloudflare R2 later means writing an `R2Storage(Storage)`
class and changing that last line. **Zero callers change.** That is the whole
point, and it is why `core/` files carry a comment saying so.

| Seam | Interface | Today's implementation | Someday |
|---|---|---|---|
| `core/storage.py` | `Storage` | `LocalStorage` (disk) | R2 / S3 |
| `core/ai_provider.py` | `AIProvider` | `MockAIProvider` | fal.ai, Segmind, … |
| `core/firebase.py` | (functions) | Firebase Admin SDK | — |
| `core/email.py` | (functions) | SMTP via Resend | — |
| `core/cache.py` | (functions) | Redis | — |

---
---

# Part III — The Chapters

Each chapter follows the same structure: **what problem it solves**, **how it
works**, **the files involved**, and — where it applies — **what it replaced**.

---

## Chapter 1 — Configuration

**Status: 🟢 CURRENT** · **File:** [`app/core/config.py`](../app/core/config.py) · **Template:** [`.env.example`](../.env.example)

### The problem

Passwords, API keys, database URLs and tuning numbers must not live in source
code. They also must not be scattered — someone setting the project up on a new
machine needs one list of everything they have to fill in.

### How it works

One Pydantic `Settings` class. Every setting is a typed field with a sensible
default. Values come from environment variables or a `.env` file, and Pydantic
**validates types at startup** — `MAX_CONCURRENT_GENERATIONS=banana` fails
immediately with a clear error instead of blowing up at 2am inside the worker.

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    DATABASE_URL: str = "sqlite:///./shootpx.db"
    MAX_CONCURRENT_GENERATIONS: int = 10
    ...

settings = Settings()   # one instance, imported everywhere
```

`.env` itself is gitignored. `.env.example` is committed and is the checklist —
copy it to `.env` and fill in the blanks.

### The settings, grouped by what they control

**Identity & URLs**
| Setting | Default | What it's for |
|---|---|---|
| `APP_NAME` | `ShootPX` | Shows up in emails and the API title |
| `ENV` | `development` | Non-`development` makes the session cookie `secure` (HTTPS-only) |
| `BACKEND_URL` | `localhost:8000` | Used to build fetchable asset URLs |
| `FRONTEND_URL` / `TEST_CONSOLE_URL` | `:3000` / `:5500` | The CORS allow-list |

**Secrets & storage**
| Setting | What it's for |
|---|---|
| `DATABASE_URL` | Postgres connection string |
| `SECRET_KEY` | Signs our session cookie. **Must** be overridden — generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `SESSION_MAX_AGE_SECONDS` | 7 days |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | Path to the gitignored Firebase key JSON |
| `STORAGE_ROOT_DIR` | Where uploaded/generated files land on disk |
| `REDIS_URL` | Queue + lock + cache, all on one Redis |

**Generation tuning** — these four are the pipeline's dials, and each one exists
for a specific reason explained in [Chapter 11](#chapter-11--the-ai-provider):
| Setting | Default | Meaning |
|---|---|---|
| `MAX_CONCURRENT_GENERATIONS` | 10 | Total jobs running at once **across every team**. Becomes arq's `max_jobs`. |
| `MOCK_GENERATION_DELAY_SECONDS` | 3 | How long the fake AI pretends to take. Irrelevant once a real provider lands. |
| `GENERATION_POLL_INTERVAL_SECONDS` | 3 | How often the worker re-checks a submitted job. Real providers bill per poll — don't set this low. |
| `GENERATION_TIMEOUT_SECONDS` | 600 | Give-up ceiling for one job's **total** lifetime. |

**Product imports** — `PRODUCT_SCRAPER_URL`, `PRODUCT_IMPORT_POLL_INTERVAL_SECONDS` (2),
`PRODUCT_IMPORT_TIMEOUT_SECONDS` (120). See [Chapter 14](#chapter-14--product-imports).

**Caches** — `LOGIN_CACHE_TTL_SECONDS` (60), `MEDIA_CACHE_TTL_SECONDS` (300).
See [Chapter 15](#chapter-15--caching).

**Email** — `SMTP_HOST/PORT/USER/PASSWORD`, `EMAIL_FROM_NAME/ADDRESS`.

> ⚠️ **Drift warning:** the *defaults in code* still say `smtp.gmail.com`, but
> `.env.example` and the real setup use **Resend** (`smtp.resend.com`, user
> `resend`, password = the `re_...` API key). The code defaults are stale. See
> [Appendix E](#appendix-e-known-documentation-drift).

---

## Chapter 2 — The Database Layer

**Status: 🟢 CURRENT** · **File:** [`app/core/db.py`](../app/core/db.py)

Eighteen lines that everything else stands on:

```python
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

Four things, each doing a distinct job:

- **`engine`** — the connection pool. One per process.
- **`SessionLocal`** — a factory for *sessions*. A session is one unit of work:
  you make changes, then `commit()` them together or throw them all away.
- **`Base`** — the registry every model class inherits from. This is how
  SQLAlchemy knows what tables exist, and why every process must import every
  model module ([see §7](#7-the-two-processes)).
- **`get_db()`** — a FastAPI *dependency*. Written as a generator so FastAPI
  runs the `finally` after the response is sent, guaranteeing the connection
  goes back to the pool even if the route raised.

**The two processes get their sessions differently, and that matters:**

| | How it gets a session | Why |
|---|---|---|
| API routes | `db: Session = Depends(get_db)` | FastAPI manages the lifecycle |
| Worker | `db = SessionLocal()` … `finally: db.close()` | No FastAPI there; does it by hand |

### A subtle trap: `expire_on_commit`

`SessionLocal` does **not** set `expire_on_commit=False`, so after `db.commit()`
SQLAlchemy marks every attribute stale and re-SELECTs it the next time you touch
it. Usually invisible. It bites when you commit a *list* of objects and then read
their ids — that's N extra queries. The bulk-generation controller works around
it explicitly:

```python
db.add_all(jobs)
db.flush()                          # assigns ids WITHOUT expiring anything
job_ids = [job.id for job in jobs]  # captured BEFORE commit
db.commit()
```

### A second subtle trap: flush ordering

SQLAlchemy orders its INSERTs based on **`relationship()` declarations**, not on
raw foreign-key columns. `Asset` has plain FK columns to `teams` and `users` but
no `relationship()` to them — so SQLAlchemy doesn't know assets must be inserted
*after* teams, and Postgres rejects the insert with a `ForeignKeyViolation`.

The fix, used in [`scripts/test_pipeline.py:76`](../scripts/test_pipeline.py#L76):
`db.flush()` after adding the parents, before adding the children. This was
reproduced for real, not theorised.

---

## Chapter 3 — The Data Model

**Status: 🟢 CURRENT** · **Files:** [`app/models/`](../app/models/)

Six tables. Here is how they connect:

```
                 ┌──────────┐
                 │  users   │  id = Firebase uid
                 └────┬─────┘
                      │
        ┌─────────────┼──────────────┬────────────────┐
        │             │              │                │
        ▼             ▼              ▼                ▼
 ┌──────────────┐  (created_by on assets, generation_jobs, product_imports)
 │ team_members │
 └──────┬───────┘
        │  role: 'owner' | 'editor'
        ▼
   ┌─────────┐         ┌───────────────┐
   │  teams  │◄────────┤ team_invites  │  pending, keyed by EMAIL
   └────┬────┘         └───────────────┘
        │
        ├──────────────────┬─────────────────────┐
        ▼                  ▼                     ▼
  ┌──────────┐    ┌──────────────────┐   ┌─────────────────┐
  │  assets  │◄───┤ generation_jobs  │   │ product_imports │
  └────▲─────┘    └──────────────────┘   └────────┬────────┘
       │            source_asset_id               │
       │            output_asset_id               │
       └──────────────────────────────────────────┘
                    product_import_id
```

### `users` — [`models/user.py`](../app/models/user.py)

One row per person, no matter how many teams they're on.

| Column | Notes |
|---|---|
| `id` | **The Firebase uid.** Not a uuid we generate. |
| `email` | Unique. This uniqueness caused a real bug — see [Chapter 4](#chapter-4--identity-and-login). |
| `name`, `avatar_url` | Nullable — Firebase doesn't always supply them |
| `created_at` | |

### `teams` + `team_members` — [`models/team.py`](../app/models/team.py)

`Team` is a workspace; its id is app-generated (`new_id()` → uuid4 string).
`TeamMembership` is the join table that makes "one person, many teams" work.

`role` is a plain string column (`'owner'` | `'editor'`), **not** a database
enum, and there is **no unique constraint** on `(team_id, user_id)` — the
application enforces no-duplicates. Deliberate: changing a DB enum requires a
migration, changing a Python enum doesn't.

> **What owners can do that editors can't:** exactly one thing today — manage
> team membership. Everything else is 🔵 deliberately undefined until real
> features need the distinction.

### `team_invites` — [`models/invite.py`](../app/models/invite.py)

Keyed by **email**, because when you invite someone who has no account, an email
address is all you have. `accepted_at` stays `NULL` until they sign in for the
first time.

### `assets` — [`models/asset.py`](../app/models/asset.py)

**One row = one file, always.** Uploaded, generated, or scraped — same table.

| Column | Notes |
|---|---|
| `team_id` | Who can access it |
| `created_by` | Who *did* it. For a generated asset that's whoever triggered the job — never "the AI" |
| `kind` | `'upload'` \| `'generated'` \| `'imported'` |
| `media_type` | `'image'` \| `'video'` — inferred from the upload's Content-Type |
| `storage_key` | What `Storage` uses internally |
| `url` | The ready-to-use, actually-fetchable link |
| `product_import_id` | 🟢 Nullable FK, set only for `kind='imported'` |

> **Why there is no "projects" table.** A deliberate product decision, not an
> oversight. The UI flow is strictly *pick a tool → generate*. A project-creation
> step would add complexity with no user-facing value. Assets and jobs scope
> straight to a team.

### `generation_jobs` — [`models/generation_job.py`](../app/models/generation_job.py)

One row per *attempt* at running a tool.

| Column | Notes |
|---|---|
| `feature_type` | Plain string. The dispatch key. Must be a registered tool ([Ch. 12](#chapter-12--the-tool-registry)) |
| `status` | `queued` \| `processing` \| `done` \| `failed` |
| `source_asset_id` / `output_asset_id` | Both nullable FKs to `assets` |
| `batch_id` | 🟢 Shared by every job from one `/generate/bulk`; null for single. **Not a FK** — there is no `batches` table |
| `external_job_id` | 🟢 The provider's own id. **NULL means "not submitted yet"** — this, not `status`, is how the worker tells the difference |
| `provider` | 🟢 Which provider handled it (`"mock"`, `"fal"`, …) |
| `input_payload` | JSON. Empty today; per-tool options land here later |
| `error`, `created_at`, `completed_at` | |

### `product_imports` — [`models/product_import.py`](../app/models/product_import.py)

Its own table rather than being bolted onto `GenerationJob`. Full reasoning in
[Chapter 14](#chapter-14--product-imports). Notable: `price` is stored as the
scraper's **raw string** (`"$49.99"`, `"₹1,299"`) rather than parsed to a number
— currency and formatting vary too much across sites to normalise reliably. And
`raw_result` keeps the scraper's entire output verbatim, so nothing is lost even
though only some fields get their own column.

---

## Chapter 4 — Identity and Login

**Status: 🟢 CURRENT** · **Files:** [`core/firebase.py`](../app/core/firebase.py), [`core/email.py`](../app/core/email.py), [`controllers/auth_controller.py`](../app/controllers/auth_controller.py), [`routes/auth_routes.py`](../app/routes/auth_routes.py)

### The division of labour (this is the confusing part)

There are two email-adjacent systems and they **do not know each other exists**:

- **Firebase** proves identity. It handles the Google popup and it *mints*
  magic-link URLs. **It sends zero emails in this project.**
- **Resend** sends every email we send. It knows nothing about auth.

### Why we send the magic-link email ourselves

Firebase has a `sendSignInLinkToEmail` that would do it for us. We don't use it.
Its sending address is the shared `noreply@<project>.firebaseapp.com`, which gets
flagged as spam. So instead we call Firebase Admin's
`generate_sign_in_with_email_link()` to *mint* the link, and then email that link
ourselves from our own verified domain.

### The full login flow

```
1. FRONTEND (Firebase JS SDK)
   ├─ Google:  signInWithPopup()
   └─ Email:   POST /auth/email-link { email, continue_url }
                 └─► backend mints a Firebase link, emails it via Resend
                     (in a BackgroundTask, so the HTTP response is instant)

2. Either path ends with the frontend holding a FIREBASE ID TOKEN.

3. Frontend: POST /auth/session { id_token }

4. Backend: core/firebase.py verify_id_token()
   The ONLY place we talk to Firebase's servers. Needs the service-account key.

5. auth_controller.upsert_user_from_firebase()   ← see the bug below

6. team_controller.accept_pending_invites()
   Any pending invite matching this email becomes a real membership. Runs on
   EVERY login regardless of which link was clicked — that's what makes
   "invite someone with no account" work.

7. Set our own signed session cookie.
   From here on, NO request touches Firebase again.
```

### 🐛 A real bug that shaped the code

`upsert_user_from_firebase` looks needlessly convoluted. It isn't:

```python
user = db.get(User, uid)                                    # 1. by Firebase uid
if not user:
    user = db.query(User).filter(User.email == email).first()  # 2. fall back to email
```

**Why the fallback exists:** Firebase's account-linking (one uid per person
across all sign-in methods) is a *project setting*, not a guarantee. Newer
Firebase projects default to **one account per provider** — meaning the *same
email address* can hand back a *different uid* depending on whether someone used
Google or the email link.

Without the fallback, the second sign-in method would try to INSERT a new row
with an email that already exists → crash on the `users.email` unique
constraint. With it, we recognise the same person and reuse their row.

The merge is also deliberately gentle: `user.name = user.name or name` — an
existing value is never overwritten by a provider that happens to supply less
information.

---

## Chapter 5 — Sessions and the Auth Gate

**Status: 🟡 CHANGED** (a cache was added in front of it — see below) · **Files:** [`core/security.py`](../app/core/security.py), [`middleware/auth.py`](../app/middleware/auth.py)

### The session token

We issue our own cookie rather than re-verifying a Firebase token on every
request (that would be a network round-trip per request).

```python
_session_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="session")

def create_session_token(user_id): return _session_serializer.dumps({"user_id": user_id})
def read_session_token(token):     ... returns user_id or None
```

**`itsdangerous`, not JWT.** Both are signed with `SECRET_KEY`, both carry an
expiry. JWT's advantage is cross-service portability, which we don't need.

The cookie itself is set with:
- `httponly=True` — JavaScript cannot read it (blocks XSS token theft)
- `secure=` **True unless ENV is development** — HTTPS-only in production
- `samesite="lax"` — meaningful CSRF protection
- `max_age=7 days`

### The gate

Every non-public route declares `current_user: User = Depends(get_current_user)`.
FastAPI runs it **before** the route body, so a bad or missing cookie never
reaches your logic at all.

### 🟡 What changed: the login cache

**Originally** `get_current_user` ran `db.get(User, user_id)` on **every single
authenticated request**, with no caching whatsoever.

**Now** it checks a Redis cache first (namespace `"login"`, 60s TTL). Full
detail in [Chapter 15](#chapter-15--caching). One consequence worth knowing here:

```python
def _from_cache(data) -> User:
    return User(id=..., email=..., ...)   # a TRANSIENT instance
```

That reconstructed `User` is **not attached to any database session**. Reading
plain columns off it (`.id`, `.email`) is fine — every current caller only does
that. Touching a **relationship** (`current_user.memberships`) would raise,
because it was never loaded and there's no session to lazy-load from. This
constraint is documented at the call site, and you must respect it.

---

## Chapter 6 — Teams, Invites and Permissions

**Status: 🟢 CURRENT** · **Files:** [`core/permissions.py`](../app/core/permissions.py), [`controllers/team_controller.py`](../app/controllers/team_controller.py)

### The permission rule

**No route or controller may ever write `if role == "owner"`.** They ask
`compute_permissions()` instead:

```python
@dataclass(frozen=True)
class Permissions:
    can_upload_assets: bool
    can_generate: bool
    can_manage_team: bool

def compute_permissions(role: str) -> Permissions:
    is_owner = role == TeamRole.owner.value
    return Permissions(
        can_upload_assets=True,    # owner AND editor, for now
        can_generate=True,         # owner AND editor, for now
        can_manage_team=is_owner,  # the one owner-only thing
    )
```

Today owner and editor share almost everything, so this looks like pointless
indirection. It isn't: when they diverge, **this is the only file that changes**.

### Two access checks, one raising and one not

```python
def get_membership(db, team_id, user_id) -> TeamMembership:
    # ...no membership → raise 404
```

**Note the 404, not 403.** Deliberate: a 403 would confirm the team exists.
A 404 reveals nothing to someone probing team ids.

```python
def has_team_access(db, team_id, user_id) -> bool:
    # same query, returns False instead of raising
```

> ⚪ **ORPHANED:** `has_team_access` was added (commit `12425e0`) for `GET /jobs`
> to silently omit inaccessible rows rather than error the whole request. The
> final implementation of `get_job_summaries` instead uses **one batched
> membership query** for all the jobs at once — better, since it avoids a query
> per job — so `has_team_access` is currently defined but **never called**.
> Harmless. A cleanup candidate, or a useful helper for the next endpoint that
> needs it. See the [Deprecation Ledger](#part-v--the-deprecation-ledger).

### The invite mechanic

`POST /teams/{id}/members` (owner-only) branches on whether the person exists:

```
Does a users row exist for this email?
├── YES → create the TeamMembership immediately. Done. (409 if already a member.)
└── NO  → create a pending TeamInvite row
          + email them a Firebase SIGN-IN LINK (not a special "invite" link)
```

**The clever bit:** the invite email *is* a sign-in link. Clicking it creates
their account, and then step 6 of the login flow
(`accept_pending_invites`) — which runs after **every** login — turns the
pending invite into a real membership. One mechanism, two outcomes, no special
"accept invite" endpoint needed.

> 🔵 **Known, deliberate limitation:** if someone is invited at
> `alice@work.com` but signs in with `alice@gmail.com`, they are correctly *not*
> auto-joined — but nothing tells them why. Fixing it properly needs invite
> context threaded through the URL, and there's no frontend to show the message
> in yet. Left as-is.

---

## Chapter 7 — Assets and Storage

**Status: 🟢 CURRENT** · **Files:** [`core/storage.py`](../app/core/storage.py), [`controllers/asset_controller.py`](../app/controllers/asset_controller.py)

### The storage seam

```python
class Storage(ABC):
    def save(self, key: str, content: bytes) -> None: ...
    def url_for(self, key: str) -> str: ...

storage: Storage = LocalStorage(root_dir=..., base_url=f"{BACKEND_URL}/files")
```

The trick that makes local storage feel real: `main.py` mounts the storage
directory as static files —

```python
app.mount("/files", StaticFiles(directory=settings.STORAGE_ROOT_DIR), name="files")
```

— so `url_for()` returns a URL you can actually open in a browser, not just a
file path. Which means swapping in R2 later changes *nothing* for API consumers;
they were always just following a URL.

### Upload

`POST /teams/{team_id}/assets`, multipart file. The controller:

1. `get_membership` → must be on the team
2. `can_upload_assets` → must be allowed
3. **Infer media type from Content-Type** — `image/*` → image, `video/*` → video,
   anything else → 400 with a clear message
4. Build a team-scoped storage key: `{team_id}/{uuid}{ext}` — team-scoped so one
   team's files never collide with another's
5. `storage.save()`, then INSERT the `Asset` row

Storage keys by kind:
| Kind | Key pattern |
|---|---|
| upload | `{team_id}/{uuid}.{ext}` |
| generated | `{team_id}/generated/{uuid}.{ext}` |
| imported | `{team_id}/imported/{uuid}.{ext}` |

> 🔵 **Not built yet:** no list-assets, update-asset, or delete-asset endpoint
> exists. This is not an accident — it's load-bearing for the media cache, which
> relies on assets being effectively immutable ([Chapter 15](#chapter-15--caching)).
> Adding a delete endpoint means adding cache invalidation at the same time.

---

## Chapter 8 — Generation Jobs

**Status: 🟡 CHANGED** — the execution model was replaced entirely. Both versions documented below.

### 🔴 Version 1: inline generation *(removed 2026-08-17, commit `32bb156`)*

> **How it originally worked:** `POST /generate` created the job row and then
> **called the AI provider right there in the request handler**, waiting for the
> result before responding. The client got back a finished job.
>
> **Why it went away:** it only worked because the mock returned instantly. With
> a real AI provider taking seconds to minutes, this design fails in three ways
> at once:
> 1. The HTTP request would hang for minutes and time out.
> 2. Each in-flight generation would pin a web worker, so a handful of users
>    would make the whole API unresponsive — including `/health`.
> 3. There would be no way to limit how many requests hit the AI provider at
>    once, and no way to stop one team monopolising it.
>
> **Replaced by:** the queue ([Chapter 9](#chapter-9--the-queue-and-the-worker)).

### 🟢 Version 2: enqueue and return *(current)*

**File:** [`controllers/generation_controller.py`](../app/controllers/generation_controller.py)

```python
async def run_generation(db, current_user, payload) -> GenerationJob:
    membership = get_membership(db, payload.team_id, current_user.id)   # on the team?
    if not compute_permissions(membership.role).can_generate: raise 403

    if payload.source_asset_id:            # asset must belong to THIS team —
        ...                                # otherwise you could generate from
                                           # another team's private image
    job = GenerationJob(status="processing", ...)
    db.add(job); db.commit()

    try:
        await enqueue_generation_job(job.id, payload.team_id)
    except Exception as exc:
        job.status = "failed"                       # ← honest failure
        job.error = f"Failed to enqueue: {exc}"
        db.commit()
        raise
    return job
```

Three details worth noticing:

**1. Status starts at `"processing"`, not `"queued"`.** The `queued` enum value
exists but is never used. Slightly odd, harmless, kept for honesty — from the
user's point of view it *is* being processed the moment they submit.

**2. The honest-failure block.** If Redis is unreachable, the enqueue throws.
Without this `except`, the job row would sit at `"processing"` **forever**, with
nothing in the universe ever going to pick it up — the worst kind of bug,
because it looks like it's working. Marking it `failed` is worse UX and far
better engineering.

**3. Cross-team asset check.** `source_asset_id` is validated against
`payload.team_id`, not just "does this asset exist".

---

## Chapter 9 — The Queue and the Worker

**Status: 🟢 CURRENT** · **Files:** [`core/queue.py`](../app/core/queue.py), [`app/worker.py`](../app/worker.py)

This is the heart of the system. Read this chapter twice.

### The enqueue side (API process)

```python
async def enqueue_generation_job(job_id: str, team_id: str) -> None:
    pool = await get_queue_pool()
    await pool.enqueue_job("run_generation_job", job_id, team_id)
```

Fire-and-forget. Note it passes **ids, not objects** — the worker re-fetches from
the database. Objects can't cross a process boundary, and by the time the worker
runs, the row may have changed anyway.

### Two independent concurrency limits

These are different mechanisms solving different problems, and conflating them
is the most common misreading of this code:

| | **Per-team lock** | **Global cap** |
|---|---|---|
| Mechanism | Redis `SET NX EX` | arq's `max_jobs` |
| Limits | 1 job per team at a time | `MAX_CONCURRENT_GENERATIONS` (10) total |
| Protects | **Fairness** — one team can't monopolise the pipeline | **The AI provider** from unlimited parallel requests |
| Configured in | `worker.py` | `WorkerSettings.max_jobs` |

> **The single most important sentence in this chapter:** the per-team lock is
> *the entire mechanism* behind bulk generation running "one after another."
> There is **no batch-runner**, no separate code path for bulk. 5 bulk jobs and
> 5 single jobs behave identically — they all queue behind the same team lock.

### The lock, in detail

```python
async def run_generation_job(ctx, job_id, team_id):
    lock_key = f"lock:team:{team_id}"

    current_holder = await redis.get(lock_key)
    if current_holder is not None and current_holder.decode() == job_id:
        await redis.expire(lock_key, LOCK_TTL_SECONDS)      # REFRESH — it's ours
    else:
        acquired = await redis.set(lock_key, job_id, nx=True, ex=LOCK_TTL_SECONDS)
        if not acquired:
            raise Retry(defer=0.5)                          # someone else has it
    ...
```

**Why refresh instead of re-acquire?** Because one job now spans many
invocations. On the second invocation, the lock key already exists (*we* set it),
so `SET NX` would fail — and the job would wrongly conclude "someone else has
it" and retry forever, deadlocked against itself.

> 🐛 **A real bug caught here:** arq's Redis client returns **bytes**, not `str`.
> Comparing `current_holder == job_id` (bytes vs str) is always `False` — which
> would have silently sent every refresh down the "someone else holds it" path
> and looped forever. Hence the `.decode()`. Found before shipping, but only by
> actually running it.

**Why `raise Retry` instead of waiting?** A job blocked on a lock must not
occupy one of the 10 global slots while it waits. `Retry` puts it back on the
queue and frees the slot immediately.

**The safe unlock.** Releasing uses a Lua script, not a plain `DEL`:

```lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else return 0 end
```

Without the check: job A overruns the 600s TTL → lock expires → job B acquires
it → job A finishes and deletes **job B's** lock → two jobs run concurrently for
that team. The Lua script makes check-and-delete atomic. This is the standard
safe-unlock pattern and it is not optional.

**`LOCK_TTL_SECONDS = 600`** is a crash guard: if a worker dies mid-job without
releasing, the team is wedged for 10 minutes, not forever. Because it's
*refreshed* every invocation, it means "600s since last touched", not "600s
total".

### `WorkerSettings`

```python
class WorkerSettings:
    functions = [run_generation_job, run_product_import]
    max_jobs = settings.MAX_CONCURRENT_GENERATIONS   # 10
    job_timeout = 300      # ONE invocation (one submit OR one poll)
    max_tries = 10_000     # see below
```

> 🐛 **Why `max_tries = 10_000`** — this looks insane and is correct. Both
> lock-contention waits and provider polls go through `arq.Retry`, and arq counts
> every `Retry` against `max_tries` (default: **5**). A job waiting behind even a
> handful of others in a bulk batch would blow through 5 retries in about two
> seconds, get **silently killed by arq** before ever reaching `_process_job`,
> and leave its row stuck at `"processing"` forever. Neither kind of retry is a
> real failure — they're just polling. The real bounds are `LOCK_TTL_SECONDS`
> and `GENERATION_TIMEOUT_SECONDS`, not this number.

### The three timeouts, which are not the same thing

| Timeout | Bounds | Value |
|---|---|---|
| `job_timeout` (arq) | **One invocation** — a single HTTP call | 300s |
| `GENERATION_TIMEOUT_SECONDS` | **One job's total lifetime**, across all its invocations | 600s |
| `LOCK_TTL_SECONDS` | How long a crashed worker wedges a team | 600s |

---

## Chapter 10 — Bulk Generation and Status Polling

**Status: 🟢 CURRENT** · **Files:** [`controllers/generation_controller.py`](../app/controllers/generation_controller.py), [`schemas/generation.py`](../app/schemas/generation.py)

### `POST /generate/bulk`

Up to **100** asset ids (`Field(min_length=1, max_length=100)`), one
`feature_type`, one shared `batch_id`. Returns immediately with the batch id and
every job id.

```python
found = db.query(Asset).filter(Asset.id.in_(payload.asset_ids),
                               Asset.team_id == payload.team_id).all()
missing = [aid for aid in payload.asset_ids if aid not in {a.id for a in found}]
if missing:
    raise HTTPException(400, f"asset_ids not found in this team: {', '.join(missing)}")
```

**All-or-nothing validation.** One bad id fails the whole request, and the error
*names the bad ids*. Better than silently generating 99 of 100.

Then the enqueue loop applies the honest-failure pattern **per job** — if Redis
blips halfway through, that one job is marked failed and the rest still get their
shot.

### `batch_id` is a string, not a table

Every job from one bulk call shares a `batch_id`; single `/generate` leaves it
`NULL`. There is no `batches` table and no foreign key. Same lightweight-string
philosophy as `feature_type`. A batch has no properties of its own — it's just a
grouping label. Adding an index if batch lookups get slow is a one-line change;
skipped for now as YAGNI at this scale.

### `GET /jobs?ids=a,b,c`

Comma-separated ids. The access check is **batched**, not per-job:

```python
jobs_by_id = {j.id: j for j in db.query(GenerationJob).filter(...in_(job_ids)).all()}
team_ids   = {j.team_id for j in jobs_by_id.values()}
accessible_team_ids = {m.team_id for m in db.query(TeamMembership).filter(
    TeamMembership.team_id.in_(team_ids), TeamMembership.user_id == current_user.id).all()}
accessible = [jobs_by_id[jid] for jid in job_ids
              if jid in jobs_by_id and jobs_by_id[jid].team_id in accessible_team_ids]
```

Two queries total, regardless of how many ids you ask about. And critically:
**inaccessible jobs are silently omitted, not errored.** Asking about 10 jobs
where one belongs to another team returns 9 — it doesn't 403 the whole request.

### `GET /batches/{batch_id}`

Returns aggregate counts plus every job:

```json
{ "batch_id": "...", "total": 5, "done": 3, "processing": 2, "failed": 0,
  "jobs": [ { "id": "...", "status": "done",
              "input":  { "url": "...", "media_type": "image" },
              "output": { "url": "...", "media_type": "image" },
              "error": null } ] }
```

Note `processing` is **computed**, not counted: `total - done - failed`. So a job
in any non-terminal state is reported as processing.

`_to_summaries()` collects every source and output asset id across all the jobs,
then resolves them in **one cached batch lookup** — this is the exact hot path
the media cache exists for ([Chapter 15](#chapter-15--caching)), because clients
poll this endpoint repeatedly while a batch runs.

---

## Chapter 11 — The AI Provider

**Status: 🟡 CHANGED** — the interface was replaced. Both versions documented.

### 🔴 Version 1: one blocking `generate()` call *(removed 2026-08-19, commit `13bef7f`)*

> **How it originally worked:**
> ```python
> class AIProvider(ABC):
>     @abstractmethod
>     def generate(self, feature_type, source_asset_url, input_payload) -> GenerationResult: ...
>
> class MockAIProvider(AIProvider):
>     def generate(self, ...):
>         return GenerationResult(media_type="image", content=_FAKE_PNG, extension="png")
> ```
> One call in, finished bytes out. The worker called it and waited.
>
> **Why it went away:** it was the wrong *shape*, and would have stayed wrong
> forever. Real AI aggregators (fal.ai, Segmind, …) are themselves asynchronous:
> you submit, get an external job id back in about a second, and the actual
> generation — seconds to minutes, much more for video — happens on their
> servers. A blocking `generate()` would mean every one of the eventual 23 tools
> pins a worker slot **idle** for the entire generation time. Ten slots, ten
> concurrent users, everyone else waits.
>
> The mock made this invisible, because it returned instantly. That's exactly why
> it was worth fixing *before* a real provider existed rather than after — the
> alternative was rewriting 23 tools later.
>
> **Replaced by:** `submit()` / `poll_result()`, below.

### 🟢 Version 2: submit and poll *(current)*

**File:** [`core/ai_provider.py`](../app/core/ai_provider.py)

```python
class AIProvider(ABC):
    @abstractmethod
    def submit(self, feature_type, source_asset_url, input_payload) -> GenerationHandle:
        """Minimum HTTP call to get an external job id. Returns in ~one request."""

    @abstractmethod
    def poll_result(self, handle: GenerationHandle) -> GenerationResult:
        """ONE status check. Raises GenerationPending if not done,
           GenerationFailed if the provider reports failure.
           NEVER loop or sleep in here — worker.py owns the cadence."""
```

Supporting types:

| Type | Role |
|---|---|
| `GenerationHandle(external_job_id, provider)` | What `submit()` returns — a reference, **not** a result |
| `GenerationResult(media_type, content, extension)` | The finished bytes |
| `GenerationPending` | **Not an error.** "Still running." Worker converts it to a `Retry`. |
| `GenerationFailed` | The provider itself reports failure. Message becomes `job.error`. |

> **A design note worth internalising:** a provider that *can* respond
> synchronously can still implement this interface trivially — `submit()` does
> the whole call, `poll_result()` returns the stored result. But a provider that
> *can't* respond synchronously must never be forced into blocking a worker slot.
> **So the interface is built around the harder case, not the easier one.** That
> is the general principle behind this whole refactor.

### The mock, and why it's cleverer than it looks

```python
class MockAIProvider(AIProvider):
    def submit(self, ...):
        ready_at = time.time() + settings.MOCK_GENERATION_DELAY_SECONDS
        return GenerationHandle(external_job_id=str(ready_at), provider="mock")

    def poll_result(self, handle):
        if time.time() < float(handle.external_job_id):
            raise GenerationPending()
        return GenerationResult("image", _FAKE_PNG, "png")
```

It **encodes the "ready at" timestamp into the external job id itself.** Why:

- It cannot `sleep()` — that would block a worker slot, defeating the entire
  point of the refactor.
- It cannot store the timestamp in a Python variable — `submit()` and
  `poll_result()` may run in **different processes**.
- A real provider's answer would live on their server. The mock has no server.
  The id is the only thing that round-trips.

And it cannot return instantly either: with a zero delay, the per-team lock would
be unobservable by polling, so nothing would prove it works.

`_FAKE_PNG` is a **real, valid, genuinely openable** 1×1 transparent PNG. Not
random bytes. The loop it proves — job → asset → a URL you can actually fetch and
open — is real, even though the "generation" is fake.

### Plugging in a real provider

1. Write `class FalProvider(AIProvider)` implementing `submit`/`poll_result`.
2. Point one or more `ToolSpec`s at an instance of it ([Chapter 12](#chapter-12--the-tool-registry)).

**Nothing in `worker.py` changes.** That is the whole design.

---

## Chapter 12 — The Tool Registry

**Status: 🟡 CHANGED** — moved and restructured. All three stages documented.

### 🔴 Stage 1: no registry at all *(removed 2026-08-19, commit `d36cd5e`)*

> **How it originally worked:** `worker.py` imported the `ai_provider` singleton
> directly and called it. Every `feature_type` hit the same provider, no matter
> what it was — and an unknown `feature_type` was silently accepted, creating a
> job that would only fail later inside the worker.
>
> **Why it went away:** with 23 tools coming, each possibly on a different
> aggregator, provider choice has to be per-tool. This was the seam for it.

### 🔴 Stage 2: `app/core/tools.py`, one flat dict *(removed 2026-08-19, commit `ea6dd4c`)*

> **How it worked:** a single file holding a dict literal:
> ```python
> TOOLS: dict[str, ToolSpec] = {
>     "on_model_shots": ToolSpec("on_model_shots", "On-Model Shots", "image", ai_provider),
>     "ugc":            ToolSpec("ugc", "UGC Video", "video", ai_provider),
> }
> ```
>
> **Why it went away:** fine for two mock entries; wrong once real tools land.
> Each real tool needs its own request-building (generic `input_payload` → that
> provider's actual request shape) and response-parsing logic — genuinely
> different per tool, not just "which provider". Keeping that in one shared file
> means **every new tool is a diff to a file 22 other tools also depend on**.
>
> **Replaced by:** the `app/tools/` package, below. The `ToolSpec` shape itself
> survived unchanged — only its home moved.

### 🟢 Stage 3: the `app/tools/` package *(current)*

**Files:** [`app/tools/`](../app/tools/)

```
app/tools/
  registry.py        ToolSpec + TOOLS dict + register() + get_tool()
                     — knows about NO specific tool
  __init__.py        imports every tool module (so they register), then
                     re-exports the registry's public names
  on_model_shots.py  ┐
  ugc.py             ┘ one file per tool, self-registering at import time
  _template.py       copy-paste starting point; leading _ so it is never
                     auto-imported and never registers itself
```

**The registration pattern** — an entire tool file:

```python
from app.core.ai_provider import ai_provider
from app.tools.registry import ToolSpec, register

register(ToolSpec(
    feature_type="on_model_shots",   # the string clients pass to /generate
    display_name="On-Model Shots",
    output_media_type="image",       # or "video"
    provider=ai_provider,
))
```

`register()` **raises loudly on a duplicate `feature_type`** at import time —
two tools silently fighting over one dispatch key is exactly the bug that should
fail at startup, not at 2am when someone finally hits the wrong one. (A dict
literal couldn't have caught this, so this is genuinely new safety, not just a
move.)

### The two places the registry is consulted

**1. At the API boundary** — [`schemas/generation.py`](../app/schemas/generation.py):
```python
if v not in known_feature_types():
    raise ValueError(f"unknown feature_type {v!r} — known: {', '.join(known_feature_types())}")
```
An unknown tool gets a **422 before a job row is ever created**, and the error
message *lists the valid options*.

**2. In the worker** — defence in depth. `_submit` and `_poll` both re-check,
in case a job reaches the worker for a `feature_type` that has since been removed
from the registry. Marks the job failed with a clear message rather than crashing.

### Adding tool #3 — the entire procedure

```bash
cp app/tools/_template.py app/tools/my_new_tool.py
# fill in feature_type / display_name / output_media_type / provider
# add ONE line to app/tools/__init__.py:
#     from app.tools import my_new_tool as _my_new_tool  # noqa: F401
```

Done. `POST /generate {"feature_type": "my_new_tool"}` works immediately. **No
route, schema, controller, or worker change.** This is the payoff the whole
chapter was building toward.

> 🔵 **Not done yet:** `output_media_type` is declared but not cross-checked
> against what the provider actually returns — there has only ever been one mock
> result shape to check against. Worth adding once a video-capable provider
> exists, so a misconfigured tool fails loudly instead of quietly mislabelling an
> asset.

---

## Chapter 13 — Database Migrations

**Status: 🟡 CHANGED** — the whole approach was replaced.

### 🔴 Version 1: `Base.metadata.create_all()` *(removed 2026-08-19, commit `9f5a928`)*

> **How it worked:** `app/main.py` called `Base.metadata.create_all(bind=engine)`
> at startup. SQLAlchemy compared the models to the database and created any
> missing tables.
>
> **Why it went away — and this is the important part:** `create_all()` **only
> ever creates missing tables. It never alters an existing one.**
>
> This failed twice in one sitting:
> 1. `batch_id` was added to `GenerationJob`. The `generation_jobs` table already
>    existed, so `create_all()` **silently did nothing**. The column had to be
>    hand-patched into the live database with raw `ALTER TABLE`.
> 2. `external_job_id` and `provider` were added. Same silent nothing. Same
>    manual `ALTER TABLE`.
>
> The silence is what makes it dangerous — no error, no warning, just a model
> and a database that quietly disagree until something breaks at runtime. Two
> occurrences was enough.
>
> **Replaced by:** Alembic.

### 🟢 Version 2: Alembic *(current)*

**Files:** [`alembic.ini`](../alembic.ini), [`alembic/env.py`](../alembic/env.py), [`alembic/versions/`](../alembic/versions/)

```bash
alembic upgrade head                              # apply all pending migrations
alembic revision --autogenerate -m "describe it"  # generate one after a model change
```

**`app/main.py` no longer creates any schema.** You must run
`alembic upgrade head` yourself before starting the app.

#### One clever bit in `alembic/env.py`

```python
from app.core.db import Base, engine     # ← the APP's engine, not alembic.ini's
```

Standard Alembic builds its own connection from `sqlalchemy.url` in
`alembic.ini`. This one imports the app's engine directly. Two reasons:

1. **`.env` stays the single source of truth** for the connection string.
2. 🐛 **ConfigParser's `%` interpolation** chokes on percent-encoded characters
   in a URL — the dev machine's Postgres password contains a literal `%40` (an
   encoded `@`), which ConfigParser tries to interpret as a substitution. Real
   bug, real fix.

`env.py` also imports **all six model modules** — the same "every model must be
registered on `Base` before mapper configuration" rule from
[§7](#7-the-two-processes). Without them, `--autogenerate` diffs against an
incomplete picture and would happily generate a migration dropping tables it
couldn't see.

#### The two migrations that exist

| Revision | What it does |
|---|---|
| `e6166cbe300b` | **Baseline.** Adopts the existing live database without a rebuild. Autogenerate found 4 pre-existing drifts — `team_members.role`, `team_members.joined_at`, `teams.created_at`, `users.created_at` were nullable in the DB but `NOT NULL` in the models. Verified there were no existing NULL rows first, then applied. A follow-up autogenerate came back **completely empty**, confirming models and DB were finally in sync. |
| `b55cfad6e50d` | Adds the `product_imports` table and `assets.product_import_id` |

> ⚠️ **Always read the generated migration before running `upgrade`.**
> Autogenerate is a *diff*, not a guarantee. It can miss things (a column rename
> looks like a drop + an add — which loses data) or include changes you didn't
> intend.

---

## Chapter 14 — Product Imports

**Status: 🟢 CURRENT** · **Files:** [`core/product_scraper_client.py`](../app/core/product_scraper_client.py), [`models/product_import.py`](../app/models/product_import.py), [`controllers/product_import_controller.py`](../app/controllers/product_import_controller.py), [`app/worker.py`](../app/worker.py)

### What it does

`POST /product-imports {team_id, url}` → scrapes a product page → gives you the
product's name, description, brand, price and theme colours, **plus every image
on the page downloaded and saved as a real `Asset`** — immediately usable as
`source_asset_id` for `/generate`, exactly like an upload.

### Three decisions, each made explicitly

**Decision 1 — the scraper is a separate service, not an import.**

`product-scrapper` is a **sibling repository** (`../product-scrapper`) with its
own `extract_product()`, independently tested (25 offline tests). It is a Python
library, so importing it directly would have been the obvious move. We didn't,
because its call **blocks for 2–25 seconds and sometimes launches a real headless
Chromium.** That is precisely the shape the `AIProvider` refactor
([Chapter 11](#chapter-11--the-ai-provider)) exists to keep out of this codebase.

Instead, that repo gained a small `service.py` — a FastAPI wrapper giving
`extract_product()` the **same submit/poll HTTP shape** as `AIProvider`:
`POST /extract {url}` returns a job id immediately (running the scrape on a
bounded thread pool so concurrent requests don't launch unbounded Chromium
instances), `GET /extract/{id}` polls. It runs as its own process
(`uvicorn service:app --port 8501`), which also keeps Chromium's weight out of
this backend's virtualenv.

**Decision 2 — `product_scraper_client` is *not* an `AIProvider`.**

It has the same `submit()`/`poll()` shape, deliberately. But it doesn't implement
the interface, because a product import's output — several images **plus**
structured data — doesn't fit `GenerationResult`'s single-image shape. Same
pattern, parallel implementation, no forced inheritance.

**Decision 3 — `ProductImport` is its own table.**

Not bolted onto `GenerationJob`, for the same reason: different output shape.
It gets promoted columns for easy querying *and* `raw_result` holding the
scraper's entire output verbatim — so nothing is ever lost, even fields that
don't have their own column (`description_bullets`, `source_layers`,
`confidence`, …).

### The worker path

`run_product_import` is `run_generation_job`'s simpler twin: identical
submit → poll → `Retry` shape, against `ProductImport` instead of
`GenerationJob`, and `product_scraper_client` instead of `AIProvider`.

**No per-team lock.** Nothing about scraping needs one team's imports serialised.
It shares the same global `max_jobs` pool as generation for now — splitting them
is 🔵 a reasonable thing to do once real traffic shows it's needed, not before.

### Once the scrape succeeds

```python
for image_url in result.get("product_images", [])[:MAX_IMPORTED_IMAGES]:  # 20
    try:
        resp = httpx.get(image_url, timeout=15.0, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        continue        # one dead/hotlink-protected image must not fail the import
    ...
    storage.save(key, content)
    db.add(Asset(kind="imported", product_import_id=imp.id, ...))
```

- **`MAX_IMPORTED_IMAGES = 20`** — a sanity ceiling, not a tuned value. A
  pathological gallery page shouldn't turn one import into hundreds of downloads.
- **One bad image is skipped, not fatal.** Dead links and hotlink protection are
  normal on the open web.
- **Extension detection** tries the URL path suffix first, then falls back to the
  `Content-Type` header, then defaults to `jpg`.

### Failure handling has two distinct paths

| Situation | Handling |
|---|---|
| Scraper *reached* the page and gave up cleanly (`blocked`, `not_a_product`, …) | Use **the scraper's own message** — it's more useful to a user than anything we'd invent |
| *Our* error (service unreachable, bad response) | `str(exc)` as the error |

### How it was verified

Both directions, for real:
- **Failure:** an unreachable-domain URL pushed through the *entire* stack —
  API → queue → worker → scraper client → wrapper service → `extract_product()`
  → back — resolving to a failed `ProductImport` carrying the scraper's own message.
- **Success:** `_poll_import` fed a synthetic `"ok"` result pointing at a real
  HTTP URL (one of this app's own stored files), confirming the `Asset` is created
  with the right `kind`/`product_import_id` and serialises correctly. A live
  third-party product page was deliberately *not* used — that isn't stable enough
  to assert against.

---

## Chapter 15 — Caching

**Status: 🟢 CURRENT** · **Files:** [`core/cache.py`](../app/core/cache.py), [`core/asset_lookup.py`](../app/core/asset_lookup.py), [`middleware/auth.py`](../app/middleware/auth.py)

### The design: namespaces, not one flat cache

```python
def _key(namespace: str, key: str) -> str:
    return f"cache:{namespace}:{key}"
```

A namespace is **just a key prefix**. That's the entire mechanism, and it buys
the one thing that matters: `clear_namespace("login")` can wipe every cached user
during an incident **without touching** anything cached under `media`.

```python
def clear_namespace(namespace: str) -> int:
    for k in client.scan_iter(match=_key(namespace, "*"), count=500):
        client.delete(k)
```

**`SCAN`, not `KEYS`.** `KEYS` blocks Redis entirely while it runs — fine on a
laptop, catastrophic in production. `scan_iter` walks incrementally.

It runs on the **same Redis** already backing the queue and the lock. And it's the
**sync** client, not `redis.asyncio`, matching this codebase's sync DB layer
throughout — no reason to mix async Redis calls into sync request handling.

### The two namespaces in use

| | **`login`** | **`media`** |
|---|---|---|
| Caches | `User` rows | `Asset` rows |
| Used by | `middleware/auth.py` | `core/asset_lookup.py` |
| Hot path | **Every single authenticated request** did a `db.get(User, …)` before this | `GET /jobs` / `GET /batches/{id}`, re-resolving the same asset ids on every poll |
| TTL | 60s | 300s |
| Write invalidation | ✅ `auth_controller.upsert_user_from_firebase` deletes the key on sign-in | ❌ **None needed** |

**Why `media` needs no invalidation:** assets are effectively **immutable** —
there is no update or delete endpoint anywhere in this application. Nothing can
go stale in a way that matters. (Note the coupling: adding a delete-asset
endpoint means adding invalidation here at the same time.)

**Why `login` invalidates rather than waiting out the TTL:** sign-in is the one
write path that can actually change a cached field (`email`, `name`,
`avatar_url`), and it happens right at the moment the user is watching. The TTL
is a *ceiling* on staleness, not the only thing keeping it correct.

### Batch-awareness on a miss

```python
def get_assets_cached(db, asset_ids: set[str]) -> dict[str, Asset]:
    for asset_id in asset_ids:
        cached = cache.get(NAMESPACE, asset_id)
        if cached is not None: result[asset_id] = _from_cache(cached)
        else:                  missing.append(asset_id)

    if missing:
        rows = db.query(Asset).filter(Asset.id.in_(missing)).all()   # ONE query
```

Check the cache per id, then **one** `IN (...)` query for everything that missed.
Never N individual queries. A cache that turned one query into N on a cold miss
would be worse than no cache.

### The ORM-instance rule

Cached values are **plain JSON dicts**, never pickled ORM instances, converted on
both sides (`_to_cache` / `_from_cache` in each caller).

A cached SQLAlchemy instance would be **detached from any `Session`**.
Reconstructing one via `Model(**dict)` is only safe as long as nothing touches a
**relationship** on it — a relationship access on a detached instance raises,
because it was never loaded and there's no session to load it from.

Every current caller only reads plain columns, and this is documented at each call
site. **If you add a caller, respect it.**

### How it was verified — the poison test

This is worth copying as a technique. For each namespace:

1. Populate the cache normally.
2. **Overwrite the cached value directly in Redis** with something the database
   does **not** contain — a fake email, a fake asset URL.
3. Hit the API. Confirm it returns **the poisoned value**. ← *This is the crucial
   step.* It proves the cache is genuinely being read, not silently bypassed.
   A cache that isn't working looks identical to one that is, unless you do this.
4. Invalidate. Confirm the real value comes back.

Also verified: `clear_namespace('login')` deletes only login's keys, leaving
media's untouched.

> 🔵 **A third namespace was explicitly considered and skipped** — a
> "central-feed" cache. There is no feed feature in this app, so there was
> nothing to cache. The namespace mechanism needs **zero changes** whenever one
> is added; a caller just starts passing a new string.

---

## Chapter 16 — Testing and the Test Console

**Status: 🟢 CURRENT** · **Files:** [`scripts/test_pipeline.py`](../scripts/test_pipeline.py), [`test-console/index.html`](../test-console/index.html)

### The honest state

> 🔵 **There is no automated test suite.** No pytest, no CI. Verification has been
> done by hand against a live database plus one end-to-end script.

That said, the verification that *has* been done is unusually rigorous — it checks
**actual database state and actual file bytes**, not just HTTP status codes.

### `scripts/test_pipeline.py`

A rerunnable end-to-end script against a **live** server. It doesn't mock
anything: real Postgres, real Redis, real worker.

**Setup:** creates a throwaway user + team + membership + 5 fake assets **directly
in Postgres**, and mints a session cookie with `create_session_token()` —
sidestepping the whole Firebase login flow, which can't be automated headlessly.

**What it proves:**

| # | Assertion | What it's really testing |
|---|---|---|
| 1 | `POST /generate/bulk` returns 201 with 5 job ids, all `processing` | Bulk submission returns immediately |
| 2 | A second single `/generate` for the **same** team also returns 201 | Submission never blocks |
| 3 | A `/generate` for a **different** team runs unblocked | The lock is **per team**, not global |
| 4 | The batch's done-count **climbs one at a time**, never jumping 0 → 5 | **The per-team lock genuinely serialises work** |
| 5 | Team A's extra single job completes **after** the batch | It was genuinely queued behind the lock |
| 6 | Team B's job is done independently | Confirms #3 from the other side |
| 7 | `GET /health` responds in well under a second | The API stays responsive while the worker is saturated |

Assertion **#4 is the heart of it** — it's the only one that can actually catch a
broken lock.

> 🐛 **A real bug this script surfaced — in the script itself.** Assertion #4 kept
> failing, and the per-team lock looked broken. It wasn't. On Windows,
> `getaddrinfo("localhost")` returns `::1` (IPv6) **before** `127.0.0.1`, and
> `urllib` tries addresses **sequentially** — no happy-eyeballs racing the way
> `curl` does. uvicorn's default `--host` binds `127.0.0.1` only, so every request
> first tried the unreachable `::1` and ate a **~2 second** timeout before falling
> back.
>
> Measured directly: 2.03s via `localhost` vs 0.005s via `127.0.0.1`.
>
> That ~2s tax, multiplied across the script's setup calls, delayed the first
> `/batches` poll until 2 of 5 jobs had **already finished** — so the assertion
> that the count climbs one-at-a-time failed because the **test client missed the
> early values**. The worker log showed jobs completing perfectly serialised,
> exactly ~3s apart, the entire time.
>
> **Fix:** `BASE_URL = "http://127.0.0.1:8000"`. A one-line change after a real
> investigation. The lesson — *when a timing test fails, suspect the test's
> timing* — is why this is written down rather than silently fixed.

### `test-console/index.html`

A deliberately bare-bones HTML page, no framework, served with
`python -m http.server 5500`. It exists because FastAPI's `/docs` **cannot drive
Firebase's browser SDK**, so the login flows are unclickable there.

Five sections:

| Section | Covers |
|---|---|
| 0. Config | Warns if `firebase-config.js` is missing |
| 1. Sign in | Google popup, magic link, `/auth/me`, logout |
| 2. Teams | Create, list, members, invites, add member |
| 3. Assets & Generation | Upload, single `/generate` |
| 4. Bulk & job status | `/generate/bulk`, `GET /jobs`, `GET /batches/{id}` |

Ids **auto-fill between sections** — `batch_id` and `job_ids` populate from the
bulk response — so you can click through a full test without copy-pasting uuids
by hand.

> **The workflow that works best:** sign in on the test console at `:5500`, then
> open `http://localhost:8000/docs` **in the same browser**. The session cookie
> carries over automatically (both are `localhost`), so `/docs` — which is far
> nicer for everything except login — becomes fully usable.

---
---

# Part IV — The Timeline

The story in the order it actually happened. Every entry is a real commit.

## Era 0 — The Foundation *(2026-08-17, commit `34aae19`)*

One commit called "first commit" containing everything that existed before the
generation pipeline work began:

- FastAPI app skeleton, MVC folder layout, CORS
- Config via Pydantic settings, `.env`
- Postgres + SQLAlchemy, schema created by `Base.metadata.create_all()` 🔴
- Firebase auth (Google + magic link), Resend email
- Our own signed session cookie
- Teams, memberships, invites, the permissions module
- Assets + local storage
- `GenerationJob` + `POST /generate` — **running inline, synchronously** 🔴
- `MockAIProvider` with a single blocking `generate()` 🔴
- The test console (sections 0–3)

**Where this left us:** a working request → job → asset loop, provably end to
end. Also three design choices that would each have to be replaced — and were,
within 48 hours.

---

## Era 1 — The Generation Pipeline *(2026-08-17)*

The single biggest push. A written plan
([`docs/superpowers/plans/2026-08-17-generation-pipeline.md`](superpowers/plans/2026-08-17-generation-pipeline.md), 1063 lines, 12 tasks)
executed task by task, one commit each.

| Commit | What landed |
|---|---|
| `ca17c1c` | The implementation plan itself, written before any code |
| `80bdb3a` | Redis/arq config + `.env.example` entries |
| `22c8948` | `batch_id` on `GenerationJob` |
| `4afa7a1` | **`app/worker.py`** — the arq worker, per-team Redis lock, global cap |
| `a04b18e` | Plan updated to record the `max_tries` discovery |
| `32bb156` | 🔴→🟢 **`/generate` enqueues instead of running inline** |
| `8b4d9e8` | Schemas for bulk + status polling |
| `12425e0` | `has_team_access` (⚪ never ended up being called) |
| `6bc4533` | Bulk generation + job/batch status controller logic |
| `8c12e1a` | Routes: `/generate/bulk`, `GET /jobs`, `GET /batches/{id}` |
| `6766d83` | README + DESIGN.md updated |
| `861a4ad` | **`scripts/test_pipeline.py`** — the end-to-end proof |
| `00ec00c` | Plan updated with two real DB-setup fixes found while testing |

### Then two real bugs, found only by actually running it

**`0778f81` — the worker couldn't query anything.**
`Team.invites` and `TeamMembership.user` are **string-based** `relationship()`
references. SQLAlchemy resolves those against whatever classes are registered on
`Base` **in the current process**. `main.py` already imported every model module
for exactly this reason — but `worker.py` imported only three of six.

Result: the very first ORM query in the worker (a `db.get` on `GenerationJob`,
which triggers full mapper configuration across the *whole* registry) raised
`InvalidRequestError`, and **every job failed permanently.** Caught by running
`test_pipeline.py` against a live stack; confirmed in the worker's traceback.

**`999725a` — the IPv6 timeout.** The `localhost` vs `127.0.0.1` bug described in
full in [Chapter 16](#chapter-16--testing-and-the-test-console). A test-harness
bug masquerading as a broken lock.

**Where this era left us:** generation is fully asynchronous, queued, per-team
fair, globally capped, and proven by an end-to-end script.

---

## Era 2 — Hardening for Reality *(2026-08-19)*

Two days later, a second session. Every commit here replaces something that
worked but wouldn't survive contact with a real AI provider.

**`dbf102e` — test console catches up.** Section 4 added: bulk generation,
`GET /jobs`, `GET /batches/{id}`, with ids auto-filling between fields.

**`13bef7f` — 🔴→🟢 AIProvider becomes submit/poll.** The big one. Full story in
[Chapter 11](#chapter-11--the-ai-provider). Added `external_job_id`/`provider`
columns, `GENERATION_TIMEOUT_SECONDS`, and fixed the lock to *refresh* rather
than re-acquire across a job's own retries — catching the bytes-vs-str comparison
bug in the process.

**`9f5a928` — 🔴→🟢 Alembic replaces `create_all()`.** After the second silent
no-op and the second manual `ALTER TABLE`. Full story in
[Chapter 13](#chapter-13--database-migrations).

**`d36cd5e` — 🔴→🟢 The tool registry.** `feature_type` now dispatches through a
registry to a per-tool provider, instead of every job hitting one global
singleton. Unknown `feature_type` becomes a 422 at the API boundary.

**`ea6dd4c` — 🔴→🟢 `core/tools.py` becomes the `app/tools/` package.** One file
per tool, self-registering, with a loud duplicate guard.

**`bb1d4d2` — 🟢 Product imports.** An entire new domain: separate scraper
service, its own client, its own table, its own worker function, its own routes.
Full story in [Chapter 14](#chapter-14--product-imports).

**`ec1f20c` — 🟢 `_template.py`.** Makes "add a tool" mechanical and foolproof.

**`0b7389b` — 🟢 The namespaced cache.** `login` and `media` namespaces, verified
with poison tests. Full story in [Chapter 15](#chapter-15--caching).

---

## Era 3 — Documentation *(2026-08-19)*

**This book.** Written after merging Era 2 from a second machine, to make the
whole history readable in one place instead of living in commit messages.

---

## Era 4 — Two Specs, Zero Code Yet *(2026-08-19)*

A real customer requirement came in — a lingerie/apparel virtual-try-on tool
(mapped directly onto the already-existing `on_model_shots` tool from Era 1;
see [Part VI](#part-vi--what-comes-next)) — which forced two questions that
had been quietly deferred since the very first commit: how does a solo user
get a team without friction, and how does anyone actually get billed.

Both were designed in full, in conversation, before any code was written —
[Spec A](superpowers/specs/2026-08-19-personal-teams-and-tools-registry-design.md)
(personal teams, tool-registry auto-discovery, a DB-backed `tools` table, a
dev-only cache API) and
[Spec B](superpowers/specs/2026-08-19-billing-credits-and-payments-design.md)
(a `PaymentProvider` seam, per-team credit ledger, monthly/yearly Razorpay
subscriptions, and a layered pricing engine built to support per-model and
per-template pricing before either of those features exists). Both specs'
self-review caught the same class of gap independently — every route either
one proposed let a client *spend* against an id it already had, none let a
client *discover* one — fixed by adding `GET /tools`, `GET /plans`, and
`GET /billing/credit-packs` before implementation ever started.

A second review pass on Spec B, checking the whole billing flow end to end
rather than each piece in isolation, found two real bugs before either had a
chance to ship: the original refill design would have left a brand-new
signup (or someone who'd just paid) waiting up to a day for their first
credits, cron-gated with nothing synchronous; and Spec B had no migration
covering teams created by Spec A before Spec B existed. Both fixed. The same
pass also surfaced three things the spec had structurally room for but never
described — webhook idempotency, atomic balance updates, and what happens
when someone wants to cancel or switch plans — and added them rather than
leaving them implicit.

Neither spec is implemented yet. This entry exists so "why does this book
suddenly know about Razorpay" has an answer.

---
---

# Part V — The Deprecation Ledger

**The graveyard.** Everything that was removed or replaced, why, and what took
its place. Nothing here is live code — this exists so nobody re-derives a
decision or wonders why a comment mentions something that doesn't exist.

### 🔴 1. Inline synchronous generation

| | |
|---|---|
| **What it was** | `POST /generate` called the AI provider inside the request handler and waited for the result |
| **Lived** | Initial commit → 2026-08-17 |
| **Removed by** | `32bb156` |
| **Why** | Only worked because the mock was instant. A real provider takes seconds to minutes → requests would time out, each generation would pin a web worker, and there'd be no way to cap load or enforce fairness |
| **Replaced by** | The arq queue + worker — [Chapter 9](#chapter-9--the-queue-and-the-worker) |
| **Still visible as** | `JobStatus.queued` exists but is never used; jobs go straight to `processing` |

### 🔴 2. `AIProvider.generate()` — the single blocking call

| | |
|---|---|
| **What it was** | `def generate(feature_type, source_asset_url, input_payload) -> GenerationResult` — one call in, finished bytes out |
| **Lived** | Initial commit → 2026-08-19 |
| **Removed by** | `13bef7f` |
| **Why** | Wrong *shape* for real aggregators (fal.ai, Segmind), which are themselves async. Every one of the eventual 23 tools would pin a worker slot idle for its entire generation time |
| **Replaced by** | `submit()` + `poll_result()` — [Chapter 11](#chapter-11--the-ai-provider) |
| **Still visible as** | `GenerationHandle`, the `external_job_id`/`provider` columns, and `MockAIProvider` encoding a timestamp into its fake job id |

### 🔴 3. `MockAIProvider` returning instantly

| | |
|---|---|
| **What it was** | The mock returned its PNG on the very first call, no delay |
| **Removed by** | `13bef7f` |
| **Why** | An instant result makes the per-team lock **unobservable by polling** — nothing would prove it works. But a `sleep()` would block a worker slot, defeating the refactor |
| **Replaced by** | Encoding a "ready at" timestamp into `external_job_id`, driven by `MOCK_GENERATION_DELAY_SECONDS` |

### 🔴 4. `Base.metadata.create_all()`

| | |
|---|---|
| **What it was** | `app/main.py` created the schema from the models at startup |
| **Lived** | Initial commit → 2026-08-19 |
| **Removed by** | `9f5a928` |
| **Why** | **It only creates missing tables — it never alters an existing one.** Failed *silently* twice in one sitting (`batch_id`, then `external_job_id`/`provider`), both needing manual `ALTER TABLE` on the live DB |
| **Replaced by** | Alembic — [Chapter 13](#chapter-13--database-migrations) |
| **Still visible as** | `main.py` still imports all six model modules — now purely for mapper registration, no longer for schema creation. The comment there says so explicitly |

### 🔴 5. Direct `ai_provider` singleton use in the worker

| | |
|---|---|
| **What it was** | `worker.py` imported the global `ai_provider` and called it; every `feature_type` hit the same provider |
| **Removed by** | `d36cd5e` |
| **Why** | 23 tools, each possibly on a different aggregator, need per-tool provider choice. Also: an unknown `feature_type` was silently accepted and only failed later inside the worker |
| **Replaced by** | The `ToolSpec` registry — [Chapter 12](#chapter-12--the-tool-registry) |

### 🔴 6. `app/core/tools.py` — the flat dict

| | |
|---|---|
| **What it was** | One file holding a `TOOLS` dict literal with a `ToolSpec` per tool |
| **Lived** | 2026-08-19 (`d36cd5e`) → 2026-08-19 (`ea6dd4c`) — a few hours |
| **Removed by** | `ea6dd4c` |
| **Why** | Fine for 2 mock entries. Once real tools land, each needs its own request-building and response-parsing logic — so **every new tool would be a diff to a file 22 other tools depend on** |
| **Replaced by** | The `app/tools/` package, one file per tool — [Chapter 12](#chapter-12--the-tool-registry) |
| **What survived** | The `ToolSpec` dataclass shape, unchanged. Only its home moved. `register()` was added, gaining a duplicate-key guard a dict literal couldn't have had |

### ⚪ 7. `has_team_access()` — orphaned, not removed

| | |
|---|---|
| **What it is** | A non-raising membership check in `core/permissions.py:47` |
| **Added by** | `12425e0`, for `GET /jobs` to silently omit inaccessible rows |
| **Status** | **Still in the code. Called by nothing.** |
| **Why** | `get_job_summaries` was ultimately implemented with **one batched membership query** for all jobs at once — strictly better, since it avoids a query per job — so the helper was never wired up |
| **What to do** | Harmless. Either delete it, or use it in the next endpoint that needs a non-raising check. Not a bug either way |

### 🔴 8. `localhost` in the test script

| | |
|---|---|
| **What it was** | `BASE_URL = "http://localhost:8000"` in `scripts/test_pipeline.py` |
| **Removed by** | `999725a` |
| **Why** | On Windows, `getaddrinfo("localhost")` returns `::1` first and `urllib` tries addresses sequentially — a ~2s timeout per request against uvicorn's IPv4-only default bind. Delayed the first poll enough to fail a timing assertion **that was actually correct** |
| **Replaced by** | `http://127.0.0.1:8000`, with a comment explaining why, so nobody "cleans it up" |

---
---

# Part VI — What Comes Next

Everything below is 🔵 **deliberately not built**, with the reasoning recorded so
it isn't re-derived.

### 🔵 Two specs already written, ready to implement

As of 2026-08-19, two full designs exist under
[`docs/superpowers/specs/`](superpowers/specs/) — reviewed, self-reviewed, not
yet implemented. This section is their pointer; the specs themselves are the
source of truth, not duplicated here.

**[Spec A — Personal Teams & Tool Registry](superpowers/specs/2026-08-19-personal-teams-and-tools-registry-design.md)**
(no dependencies, can start immediately):
- Auto-create a personal team the moment someone signs up, so `team_id` is
  never a blocker for a solo user — replaces the current "you must manually
  call `POST /teams` first" behavior described in
  [Chapter 6](#chapter-6--teams-invites-and-permissions).
- `PATCH /teams/{id}` (rename, owner-only) and `GET /tools` (list every
  active tool) — two routes this codebase has never had.
- `app/tools/` auto-discovery — adding a tool stops needing an
  `__init__.py` edit at all, extending
  [Chapter 12](#chapter-12--the-tool-registry)'s "one file per tool" further
  than it goes today.
- A DB-backed `tools` table (`credit_cost`, `is_active`, `pricing_config`) —
  code stays the source of truth for *behavior*, the DB becomes editable
  without a redeploy for *cost and kill-switches*.
- A dev-only cache-clear API (`POST /admin/cache/clear`, `ENV=development`
  only) — extends [Chapter 15](#chapter-15--caching)'s manual one-liner into
  something the test console can actually click.
- Removes `has_team_access()` ([Deprecation Ledger #7](#part-v--the-deprecation-ledger)) —
  the first entry in that ledger to go from ⚪ orphaned to actually deleted.

**[Spec B — Billing: Payments, Credits, Dynamic Pricing](superpowers/specs/2026-08-19-billing-credits-and-payments-design.md)**
(depends on Spec A):
- A `PaymentProvider` seam — Razorpay first, built the same way `Storage` and
  `AIProvider` were ([§8](#8-the-swappable-seam-pattern)) so Stripe/PayPal
  are a new file later, not a rewrite.
- Per-team credit balances (confirmed decision: **per-team, not per-user** —
  matches every other resource in this app being team-scoped) with a
  full audit ledger (`credit_transactions`), monthly/yearly subscriptions,
  and one-off top-ups.
- A layered pricing engine: flat tool cost today → per-model base cost +
  tool-specific modifiers (resolution, etc.) → optional per-template
  override — so a future multi-model tool or template feature prices itself
  without touching this engine again.
- Credit cost is **resolved once, at submission, and stored on the job** —
  never recomputed at completion — so a mid-flight pricing change can never
  retroactively affect a job already running.
- Monthly credit refills run off an **independent arq cron job**, not
  provider webhooks — a yearly Razorpay subscription only fires one charge
  event a year, which can't drive a monthly refill on its own. **The very
  first grant is synchronous, not cron-driven** — a second review pass
  caught that the original draft would have left a brand-new signup at zero
  credits for up to a day, waiting on the next daily tick.
- Webhook processing is **idempotent** (checked against `payments` before any
  credit grant — providers redeliver events at-least-once) and credit
  balance updates are **atomic SQL**, not read-then-write — a webhook-driven
  grant and a worker-driven deduction can land at the same moment, and only
  deductions are protected by the existing per-team generation lock.
- New routes: `GET /plans`, `GET /billing/credit-packs`, `POST /billing/subscribe`
  (doubles as a plan-change when one's already active), `POST /billing/cancel`
  (effective at period end, never instant), `POST /billing/topup`,
  `POST /billing/webhook/{provider}` (also handles refunds, reactively —
  refunds are issued from Razorpay's own dashboard, not our API), `GET /billing/teams/{id}`.
- A second Alembic migration backfills the Free plan onto every team that
  already exists by the time this spec ships — Spec A creates real teams
  before Spec B exists, and nothing else would catch them.

### 🔵 Every missing API, catalogued

Beyond the two specs above, a pass through what a real product needs (and what
platforms like Photoroom/Claid/Higgsfield already have) surfaces API gaps with
no spec yet:

| Missing API | Why it matters | Status |
|---|---|---|
| `GET /tools`, `GET /plans`, `GET /billing/credit-packs` | Every route added so far lets you *spend* against an id you already know — nothing lets a client *discover* one | ✅ Caught in spec self-review, now in Spec A/B above |
| API keys for programmatic access | A real B2B customer (see the lingerie-tool example) wants to integrate directly, not click through a browser. Right now the *only* auth path is the Firebase-popup + session-cookie flow — there is no way for a server-to-server caller to authenticate at all | Not yet spec'd |
| Webhooks for job completion | `GET /jobs` polling works, but every comparable platform also offers "tell me when it's done" instead of making the client poll forever | Not yet spec'd |
| Asset list / delete | Upload exists; there's no way to browse or remove your own files | Not yet spec'd. ⚠️ Delete requires adding media-cache invalidation at the same time ([Ch. 15](#chapter-15--caching)) |
| Team member removal / leave-team | You can invite; nothing lets you remove a member or leave a team you're on | Not yet spec'd |
| Team delete | No such endpoint exists | Not yet spec'd — deliberately out of scope in Spec A too |
| User profile update / account deletion | No `PATCH /auth/me`, no way to delete your own account (GDPR-relevant once real people's photos are involved — see the content-safety note this session raised for the lingerie tool) | Not yet spec'd |
| Usage/analytics endpoints | No `GET /teams/{id}/usage` — nothing surfaces credits spent over time or jobs-by-status, needed for any real dashboard | Not yet spec'd |
| Admin/ops visibility beyond cache-clear | No cross-team usage view, no real admin surface at all outside Spec A's one dev-only endpoint | Not yet spec'd |
| Content moderation (input + output) | Real risk once a tool generates images of real people in intimate apparel from arbitrary uploads — flagged explicitly when the lingerie-tool requirement came in | Not yet spec'd — a product/legal decision as much as an engineering one |

### The big one: a real AI provider

Everything exists to make this a contained change:

1. Write `class FalProvider(AIProvider)` (or Segmind, or whatever) implementing
   `submit()` and `poll_result()`.
2. Point `ToolSpec.provider` at an instance of it, per tool.
3. Delete nothing. Change no plumbing.

Per-tool request-building (generic `input_payload` → that provider's actual
request shape) and response-parsing live **in that tool's own file** in
`app/tools/`. Nothing shared gets more crowded as tools are added.

### The other 21 tools

Two of 23 exist (`on_model_shots`, `ugc`), both on the mock. Adding one is:
copy `_template.py`, fill in four fields, add one import line.

### Known gaps, ranked by how much they'd hurt

| Gap | Why it matters | Notes |
|---|---|---|
| **No automated test suite** | The single biggest risk. All verification is manual or one script | `scripts/test_pipeline.py` is a good skeleton to grow from |
| **Cloud storage (R2/S3)** | Local disk doesn't survive a deploy | One-file change behind the `Storage` seam ([§8](#8-the-swappable-seam-pattern)) |
| **`output_media_type` unchecked** | A misconfigured tool would quietly mislabel an asset | Add the cross-check once a video-capable provider exists |
| **No asset list/delete endpoints** | Users can't manage their own files | ⚠️ Adding delete **requires** adding media-cache invalidation at the same time ([Ch. 15](#chapter-15--caching)) |
| **Owner vs editor undefined** | Only team management is owner-only today | Change `compute_permissions()` — and **only** that file |
| **Transient vs permanent errors** | A network blip fails a job permanently, same as a real error | Deliberately deferred until a real provider's actual failure modes are known |
| **Invite-email-mismatch messaging** | Someone invited at one address who signs in with another is silently not joined | Needs invite context in the URL; no frontend to show it in yet |
| **Imports share generation's job pool** | A burst of imports competes with generation | Split the cap once real traffic shows it's needed |
| **Billing / subscriptions** | Not started in code | Fully designed — [Spec B](superpowers/specs/2026-08-19-billing-credits-and-payments-design.md) |
| **Real frontend** | Only the test console exists | |

### Things explicitly considered and rejected

- **A `projects` layer** — the UI flow is *pick a tool → generate*. A project step
  adds complexity with no user-facing value.
- **A `batches` table** — a batch has no properties of its own. A shared string is
  enough.
- **A `central-feed` cache namespace** — there is no feed feature to cache.
- **Importing `product-scrapper` directly** — it blocks 2–25s and launches
  Chromium. It gets a service wrapper instead.
- **A database enum for `role`** — changing a DB enum needs a migration; a Python
  enum doesn't.
- **An index on `batch_id`** — YAGNI at this scale. One line to add later.

---
---

# Part VII — Appendices

## Appendix A: Complete File Map

```
shootpx-backend/
├── alembic.ini                     Alembic config (its sqlalchemy.url is NOT used — see env.py)
├── alembic/
│   ├── env.py                      🟢 Imports the APP's engine + all 6 models
│   └── versions/
│       ├── e6166cbe300b_...py      Baseline — adopts the pre-existing live DB
│       └── b55cfad6e50d_...py      Adds product_imports + assets.product_import_id
│
├── app/
│   ├── main.py                     Creates the app, mounts /files, registers 6 routers
│   ├── worker.py                   🟢 THE WORKER PROCESS — lock, submit/poll, Retry
│   │
│   ├── core/                       ── infrastructure & swappable seams ──
│   │   ├── config.py               All settings, one Pydantic class
│   │   ├── db.py                   engine, SessionLocal, Base, get_db()
│   │   ├── security.py             Session cookie signing (itsdangerous)
│   │   ├── firebase.py             Admin SDK: verify tokens, mint magic links
│   │   ├── email.py                SMTP send (via Resend)
│   │   ├── storage.py              🔌 Storage interface + LocalStorage
│   │   ├── ai_provider.py          🔌 AIProvider (submit/poll) + MockAIProvider
│   │   ├── product_scraper_client.py  submit/poll client for the scraper service
│   │   ├── queue.py                arq pool + the two enqueue functions
│   │   ├── cache.py                Namespaced Redis cache
│   │   ├── asset_lookup.py         Cached, batch-aware Asset lookups ("media")
│   │   └── permissions.py          compute_permissions, get_membership, has_team_access ⚪
│   │
│   ├── tools/                      ── the 23-tools registry ──
│   │   ├── registry.py             ToolSpec, TOOLS, register(), get_tool()
│   │   ├── __init__.py             Imports every tool so it registers
│   │   ├── on_model_shots.py       Tool 1
│   │   ├── ugc.py                  Tool 2
│   │   └── _template.py            Copy-paste starter (leading _ = never auto-imported)
│   │
│   ├── middleware/
│   │   ├── auth.py                 get_current_user — the login gate + login cache
│   │   └── setup.py                CORS registration
│   │
│   ├── models/                     ── SQLAlchemy tables ──
│   │   ├── user.py                 users (id = Firebase uid)
│   │   ├── team.py                 teams + team_members + TeamRole + new_id()
│   │   ├── invite.py               team_invites (keyed by email)
│   │   ├── asset.py                assets (upload | generated | imported)
│   │   ├── generation_job.py       generation_jobs
│   │   └── product_import.py       product_imports
│   │
│   ├── schemas/                    ── Pydantic request/response shapes ──
│   │   ├── auth.py  teams.py  assets.py  generation.py  product_import.py
│   │
│   ├── controllers/                ── THE ACTUAL LOGIC ──
│   │   ├── auth_controller.py      upsert user, session cookie, magic-link email
│   │   ├── team_controller.py      create/list teams, add member, accept invites
│   │   ├── asset_controller.py     upload
│   │   ├── generation_controller.py  single + bulk generate, job/batch status
│   │   └── product_import_controller.py
│   │
│   └── routes/                     ── thin URL → controller wiring ──
│       ├── health_routes.py  auth_routes.py  team_routes.py
│       ├── asset_routes.py   generation_routes.py  product_import_routes.py
│
├── scripts/test_pipeline.py        End-to-end proof against a LIVE server
├── test-console/index.html         Hand-driven UI (5 sections)
├── docs/
│   ├── BOOK.md                     ← you are here
│   ├── superpowers/plans/2026-08-17-generation-pipeline.md
│   └── superpowers/specs/          Written, reviewed, not-yet-built designs
│       ├── 2026-08-19-personal-teams-and-tools-registry-design.md
│       └── 2026-08-19-billing-credits-and-payments-design.md
├── README.md                       Setup + day-to-day usage
├── DESIGN.md                       Architecture reference + decision rationale
├── .env.example                    The setup checklist
└── requirements.txt
```

**Legend:** 🔌 = a swappable seam · ⚪ = orphaned

---

## Appendix B: Every Route

| Method | Path | Auth | Does |
|---|---|---|---|
| `GET` | `/health` | — | Liveness check |
| `GET` | `/` | — | Name + "is running" |
| `GET` | `/files/*` | — | Static: serves whatever `LocalStorage` wrote |
| `POST` | `/auth/email-link` | — | Mints a Firebase link, emails it (background task) |
| `POST` | `/auth/session` | — | **This is the login call.** Verify token → upsert user → accept invites → set cookie |
| `GET` | `/auth/me` | ✅ | Who am I |
| `POST` | `/auth/logout` | ✅ | Clears the cookie |
| `POST` | `/teams` | ✅ | Create a team; you become `owner` |
| `GET` | `/teams` | ✅ | Your teams + your role in each |
| `GET` | `/teams/{id}/members` | ✅ member | The roster |
| `GET` | `/teams/{id}/invites` | ✅ member | Still-pending invites |
| `POST` | `/teams/{id}/members` | ✅ **owner** | Direct-add if they have an account, else pending invite + email |
| `POST` | `/teams/{id}/assets` | ✅ + `can_upload_assets` | Multipart upload |
| `POST` | `/generate` | ✅ + `can_generate` | Enqueue one job. **Returns immediately** |
| `POST` | `/generate/bulk` | ✅ + `can_generate` | Up to 100 assets, one `feature_type`, shared `batch_id` |
| `GET` | `/jobs?ids=a,b,c` | ✅ | Poll many jobs. **Silently omits** inaccessible ones |
| `GET` | `/batches/{batch_id}` | ✅ member | Aggregate counts + every job |
| `POST` | `/product-imports` | ✅ + `can_upload_assets` | Enqueue a scrape. Returns immediately |
| `GET` | `/product-imports/{id}` | ✅ member | Poll; once done includes metadata + every image as a real asset |

### 🔵 Planned routes — not built yet

Everything below is designed, not live. Calling any of these today 404s.
Spec-backed rows link to their spec; everything else is a catalogued gap with
no spec written ([Part VI](#part-vi--what-comes-next) has the full reasoning).

| Method | Path | Spec |
|---|---|---|
| `PATCH` | `/teams/{id}` | [Spec A](superpowers/specs/2026-08-19-personal-teams-and-tools-registry-design.md) |
| `GET` | `/tools` | [Spec A](superpowers/specs/2026-08-19-personal-teams-and-tools-registry-design.md) |
| `POST` | `/admin/cache/clear` | [Spec A](superpowers/specs/2026-08-19-personal-teams-and-tools-registry-design.md) |
| `GET` | `/plans` | [Spec B](superpowers/specs/2026-08-19-billing-credits-and-payments-design.md) |
| `GET` | `/billing/credit-packs` | [Spec B](superpowers/specs/2026-08-19-billing-credits-and-payments-design.md) |
| `POST` | `/billing/subscribe` | [Spec B](superpowers/specs/2026-08-19-billing-credits-and-payments-design.md) |
| `POST` | `/billing/topup` | [Spec B](superpowers/specs/2026-08-19-billing-credits-and-payments-design.md) |
| `POST` | `/billing/webhook/{provider}` | [Spec B](superpowers/specs/2026-08-19-billing-credits-and-payments-design.md) |
| `GET` | `/billing/teams/{id}` | [Spec B](superpowers/specs/2026-08-19-billing-credits-and-payments-design.md) |
| — | API keys (server-to-server auth) | not yet spec'd |
| — | Job-completion webhooks | not yet spec'd |
| — | Asset list / delete | not yet spec'd |
| — | Team member removal / leave-team / delete-team | not yet spec'd |
| — | User profile update / account deletion | not yet spec'd |
| — | Usage/analytics endpoints | not yet spec'd |
| — | Content moderation (input + output) | not yet spec'd |

**Status codes used deliberately:**
- `201` for every create
- `400` — a source asset doesn't belong to the team; unsupported file type
- `401` — bad/missing session cookie
- `403` — you're on the team but lack the permission
- `404` — **you're not on the team** (deliberately not 403, so team ids can't be probed); or the batch/import doesn't exist
- `409` — already a member / already invited
- `422` — Pydantic rejected the body (including an unknown `feature_type`)

---

## Appendix C: Glossary

| Term | Meaning here |
|---|---|
| **Asset** | One file. Uploaded, generated, or scraped — always one row in `assets` |
| **arq** | The Redis-backed task queue library. Provides `Retry` |
| **Batch** | A group of jobs from one `/generate/bulk`. Just a shared string, no table |
| **Detached instance** | A SQLAlchemy object with no live `Session`. Safe to read columns from; **raises** on relationship access |
| **`external_job_id`** | The *provider's* id for a job. `NULL` means "not submitted yet" |
| **`feature_type`** | The dispatch key naming which tool to run. Must be registered |
| **Flush vs commit** | `flush()` sends SQL and assigns ids but doesn't finalise; `commit()` finalises and expires attributes |
| **Global cap** | `MAX_CONCURRENT_GENERATIONS` → arq's `max_jobs`. Total jobs across all teams |
| **Handle** | A reference to work happening elsewhere (`GenerationHandle`, `ScrapeHandle`) |
| **Invocation** | One execution of a worker function. A single job spans **many** |
| **Namespace** | A cache key prefix. Lets one concern be cleared without touching another |
| **Per-team lock** | A Redis key ensuring one generation per team at a time. The **entire** mechanism behind bulk running one-at-a-time |
| **Poison test** | Overwrite a cached value with something the DB lacks, then confirm the API returns it — proving the cache is genuinely read |
| **Read-through cache** | Check cache → on miss, hit DB and populate cache |
| **`Retry`** | arq's "put me back on the queue and free my slot." Used for both lock-waiting and provider-polling |
| **Seam** | An interface + one implementation + one module-level instance, so the implementation can be swapped |
| **Submit/poll** | Hand work to an external system, get an id, check back later. Never block |
| **`ToolSpec`** | One tool's registry entry: `feature_type`, `display_name`, `output_media_type`, `provider` |
| **Transient instance** | A model object built with `Model(**dict)`, never queried. Same caveats as detached |
| **Upsert** | Update if it exists, insert if it doesn't |

---

## Appendix D: How to Append to This Book

**Follow this every time the code changes. The book must never shrink.**

### Case 1 — You added something new

1. Add a chapter at the end of Part III, marked 🟢 **CURRENT**, following the
   standard shape: *the problem → how it works → the files → what it replaced*.
2. Add it to the Table of Contents.
3. Add a Timeline entry in Part IV with the commit hash and date.
4. If it introduces a new file, add it to [Appendix A](#appendix-a-complete-file-map).
5. If it introduces a route, add it to [Appendix B](#appendix-b-every-route).
6. If it introduces jargon, add it to [Appendix C](#appendix-c-glossary).

### Case 2 — You changed or replaced something

**Do not edit the old text. This is the whole point of the book.**

1. Find the existing section. Change its badge from 🟢 to 🟡 **CHANGED**.
2. **Wrap the old description in a blockquote**, retitle it
   `### 🔴 Version N: <name> *(removed YYYY-MM-DD, commit hash)*`, and add:
   ```markdown
   > **Why it went away:** <the real reason — what actually broke, or what
   > would have broken. Not "it was refactored".>
   >
   > **Replaced by:** <link to the new version>
   ```
3. Write the new version **directly underneath**, as
   `### 🟢 Version N+1: <name> *(current)*`.
4. Add a numbered entry to the [Deprecation Ledger](#part-v--the-deprecation-ledger)
   with the standard table: *what it was · lived · removed by · why · replaced by ·
   still visible as*.
5. Add a Timeline entry.

Use [Chapter 11](#chapter-11--the-ai-provider) and
[Chapter 13](#chapter-13--database-migrations) as worked examples — they both do
exactly this.

### Case 3 — You deleted something entirely

Same as Case 2, but there is no replacement. Mark the section 🔴, keep every word
of it, and say plainly what fills the gap now (or that nothing does).

### Case 4 — Something became unused but still exists

Mark it ⚪ **ORPHANED** in place, add a note explaining why nothing calls it, and
add a ledger entry. See `has_team_access` in
[Chapter 6](#chapter-6--teams-invites-and-permissions) as the worked example.

### The house style

- **Explain *why*, not just *what*.** The code already says what. A reader can
  read the code; they can't read the decision.
- **Name the bug.** If something looks strange because of a real failure, say so
  and describe the failure. Every 🐛 marker in this book is a real, reproduced
  bug — that is what makes them worth reading.
- **Link to files** as `[path](../path)` so they're clickable.
- **Write for someone who has never seen this codebase.** No unexplained jargon;
  if you must use it, add it to the glossary.
- **Be honest about gaps.** 🔵 markers are more useful than silence.

---

## Appendix E: Known Documentation Drift

Small inaccuracies found in the codebase while writing this book. None are bugs
— all are stale comments. Recorded so nobody trusts them.

| Where | What it says | What's actually true |
|---|---|---|
| [`core/email.py`](../app/core/email.py) docstring | "Send an email through **Gmail** SMTP… must be a Gmail address + App Password" | Email goes through **Resend** (`smtp.resend.com`, user `resend`, password = the `re_...` API key). See `.env.example` |
| [`core/email.py`](../app/core/email.py) trailing comment | "Login itself is Google-only. This helper is kept around because the next natural feature — emailing someone when they're added to a team — will want it; **nothing calls it yet**" | Both claims are stale. Magic-link login exists, and `send_email` **is** called — by `auth_controller` and `team_controller` |
| [`core/config.py`](../app/core/config.py) SMTP defaults | `SMTP_HOST = "smtp.gmail.com"` | `.env.example` and real setup use `smtp.resend.com`. The code default is a leftover; `.env` overrides it |
| [`models/generation_job.py`](../app/models/generation_job.py) docstring | "today every `feature_type` just hits the same `MockAIProvider`" | Still true in effect, but it now goes **through the tool registry** to get there, not directly ([Ch. 12](#chapter-12--the-tool-registry)) |
| `JobStatus.queued` | Implies jobs start as `queued` | Never used. Jobs are created as `processing` |

---

<div align="center">

**End of the ShootPX Backend Book.**

*Last chapter: [Chapter 16](#chapter-16--testing-and-the-test-console) ·
Last commit covered: 2026-08-19, `0b7389b` ·
Last timeline entry: Era 4, 2026-08-19 — two specs written, neither implemented yet.*

**When you change the code, [append to this book](#appendix-d-how-to-append-to-this-book).**

</div>


