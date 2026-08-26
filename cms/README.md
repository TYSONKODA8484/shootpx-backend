# ShootPX CMS

Internal control panel — view and edit every table in the ShootPX database:
users, teams, plans, subscriptions, credits, tools, generation jobs, and
more. Not customer-facing. Built to be fast to build and fast to use, not
pretty.

## Running it

1. Make sure the backend is running first (`uvicorn app.main:app --reload`
   from the repo root) and has `CMS_ADMIN_PASSWORD` set in its `.env`.
2. `cd cms`
3. `npm install`
4. Copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_BACKEND_URL` if
   the backend isn't on `http://localhost:8000`.
5. `npm run dev` — runs on `http://localhost:3001`.
6. Open `http://localhost:3001`, enter the admin password.

## How auth works

One shared password (`CMS_ADMIN_PASSWORD` in the backend's `.env`), not a
per-user login. `POST /cms/login` checks it and sets an httponly
`cms_session` cookie (signed with the backend's `SECRET_KEY`, 7-day expiry).
Every `/cms/*` data route requires that cookie. There's no "who edited
what" audit trail — this is single-operator tooling, not a multi-admin
system.

The `SameSite=Lax` cookie works across the two dev ports (`3001` and
`8000`) because both are `localhost` — same "site," different origin. A
real deployment on two different domains would need `SameSite=None` +
`Secure` (HTTPS) instead, or a reverse-proxy that makes them same-site.

## API reference

All routes below live on the **backend** (`NEXT_PUBLIC_BACKEND_URL`), under
`/cms`. All except `/cms/login` require the `cms_session` cookie.

| Method | Path | What it does |
|---|---|---|
| POST | `/cms/login` | `{"password": "..."}` → sets the session cookie |
| POST | `/cms/logout` | Clears the session cookie |
| GET | `/cms/me` | `{"authenticated": true}` or 401 |
| GET | `/cms/entities` | Every registered entity's field schema — drives every generic page in this app |
| GET | `/cms/stats` | Dashboard counts (users, teams, subscriptions by plan, total credit balance) |
| GET | `/cms/entities/{entity}?page=&search=` | Paginated (50/page) list; `search` matches that entity's `search_fields` |
| POST | `/cms/entities/{entity}` | Create a row (405 if the entity doesn't allow it, e.g. `tools`) |
| GET | `/cms/entities/{entity}/{id}` | One row |
| PATCH | `/cms/entities/{entity}/{id}` | Partial update — 400 if any field isn't editable |
| DELETE | `/cms/entities/{entity}/{id}` | Hard delete — 400 if it violates a foreign key elsewhere |

`{entity}` is one of: `users`, `teams`, `team-memberships`, `team-invites`,
`plans`, `team-subscriptions`, `team-credit-balances`, `credit-transactions`
(create-only — no PATCH/DELETE), `credit-packs`, `tools` (read-only:
`feature_type`/`display_name`/`output_media_type` are managed by the
backend's tool registry, not editable here — see `app/models/tool.py`),
`ai-models`, `assets`, `generation-jobs`, `product-imports`, `payments`,
`templates`, `nav-items` (read-only `key`/`label` — the 12 Studio sidebar
pages, seeded once by migration; toggle `is_active` to show/hide a whole
page in the Studio app, same mechanism as `tools.is_active`).

## Known limitations (v1)

- Deleting a row with dependents elsewhere fails loudly (400) instead of
  cascading — check the entity's related tables first if a delete fails.
- Editing `team-credit-balances.balance` directly does **not** create a
  matching `credit-transactions` row — prefer creating a
  `credit-transactions` entry (it's append-only/auditable) unless you're
  specifically fixing a desync between the two.
- Foreign-key fields are plain text inputs (paste the target row's id) —
  no searchable dropdown. Open the target entity's table in another tab to
  find the id.
- No audit log of who changed what (there's no "who" — shared password).
- Pinned to Next.js 14.2.15, which has several known CVEs (mostly DoS/cache
  poisoning affecting server-exposed deployments). Acceptable for a
  localhost-only, single-operator internal tool; **upgrade before ever
  exposing this beyond localhost** (`npm audit` for details — a 15.x/16.x
  upgrade is a breaking change not attempted in this v1).
