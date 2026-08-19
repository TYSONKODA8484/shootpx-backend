# Spec B — Billing: Multi-Provider Payments, Credits, Dynamic Pricing

**Status:** Ready for review
**Depends on:** Spec A (`create_personal_team`, the `tools` table, `Tool.default_model_id`)

## Why

Real customers need real billing. This spec builds: recurring subscriptions
(monthly/yearly) plus one-off credit top-ups, all metered against a per-team
credit balance, priced by a layered engine that can price a flat tool today
and a multi-model/template tool later without redesign — and built behind a
payment-provider seam so Razorpay isn't a permanent architectural commitment.

## Section 1 — The payment provider seam

Same swappable-seam pattern already used twice in this codebase (`Storage`,
`AIProvider` — BOOK.md §8). One interface, one implementation today:

```python
# app/core/payment_provider.py
class PaymentProvider(ABC):
    @abstractmethod
    def create_subscription(self, team_id: str, plan: "Plan") -> SubscriptionHandle: ...
    @abstractmethod
    def create_one_time_order(self, team_id: str, amount: int, currency: str) -> OrderHandle: ...
    @abstractmethod
    def cancel_subscription(self, provider_subscription_id: str) -> None: ...
    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool: ...

class RazorpayProvider(PaymentProvider):
    ...  # today's only implementation

payment_provider: PaymentProvider = RazorpayProvider()
```

Every table that references an external payment record stores **both** a
`provider` string and a `provider_*_id` — mirroring `GenerationJob.provider`/
`external_job_id` exactly, not inventing a new naming convention. Adding
Stripe later means: `class StripeProvider(PaymentProvider)`, a new row per
plan with `provider="stripe"`, a new webhook route
(`/billing/webhook/stripe`) — **zero changes to any shared billing logic**,
same story as adding a tool or swapping storage.

## Section 2 — Data model

Table names avoid colliding with the `app/models/` Python package — the AI
model catalog table is `ai_models`, not `models`.

**`plans`**
| Column | Notes |
|---|---|
| `id` (PK) | |
| `name` | e.g. "Free", "Starter" — actual tiers/pricing are business data, not invented here; seeded with one placeholder Free plan only |
| `billing_cycle` | `'monthly'` \| `'yearly'` \| `'free'` |
| `price` | smallest currency unit (paise); null for Free |
| `currency` | default `'INR'` |
| `credit_allowance` | credits granted **per monthly refill**, regardless of billing_cycle (see Section 4) |
| `max_team_members` | hard cap, enforced in `team_controller.add_member` |
| `provider` | e.g. `'razorpay'`; null for Free (no payment provider involved) |
| `provider_plan_id` | the provider's own plan id; null for Free |
| `is_active` | retiring a plan without deleting it — existing subscribers keep referencing the row |
| `created_at` | |

**`team_subscriptions`** — one per team
| Column | Notes |
|---|---|
| `id` (PK) | |
| `team_id` (FK, unique) | one active subscription per team |
| `plan_id` (FK) | |
| `provider` / `provider_subscription_id` | null while on Free |
| `status` | `'active'` \| `'past_due'` \| `'cancelled'` \| `'free'` |
| `current_period_end` | null for Free |
| `next_credit_refill_at` | drives the refill cron (Section 4) — set for **every** team, Free included |
| `created_at`, `updated_at` | |

**`team_credit_balances`** — `team_id` (PK/FK), `balance`, `updated_at`. The
fast-read number `/generate` checks. **Derived from, and always reconcilable
against, `credit_transactions` below** — never the sole source of truth.

**`credit_transactions`** — the ledger, append-only
| Column | Notes |
|---|---|
| `id` (PK) | |
| `team_id` (FK) | |
| `amount` | signed (+grant/-spend) |
| `reason` | `'plan_grant'` \| `'topup_purchase'` \| `'generation_spend'` \| `'refund'` \| `'manual_adjustment'` |
| `reference_id` | job id / payment id, depending on `reason` |
| `balance_after` | snapshot, so support/audits never need to replay history |
| `created_at` | |

**`credit_packs`** — purchasable top-up amounts. `id`, `name`, `credit_amount`,
`price`, `currency`, `is_active`. No provider-side pre-registration needed —
one-time orders are created with an arbitrary amount directly.

**`payments`** — our own record of every provider charge processed, for
reconciliation without re-querying the provider
| Column | Notes |
|---|---|
| `id` (PK) | |
| `team_id` (FK) | |
| `provider` / `provider_payment_id` (unique) | |
| `provider_order_id` or `provider_subscription_id` | whichever applies |
| `amount`, `currency` | |
| `status` | `'captured'` \| `'failed'` \| `'refunded'` |
| `kind` | `'subscription_charge'` \| `'topup'` |
| `created_at` | |

**`ai_models`** — the model-playground catalog
| Column | Notes |
|---|---|
| `model_id` (PK) | |
| `display_name` | |
| `base_credit_cost` | DB-editable |
| `provider_name` | which AI aggregator (fal.ai, Segmind, …) — independent of `PaymentProvider`, this is about generation, not billing |
| `is_active` | |

**`templates`** — presets that can override computed pricing entirely
| Column | Notes |
|---|---|
| `template_id` (PK) | |
| `feature_type` (FK → `tools`) | |
| `model_id` (nullable FK → `ai_models`) | |
| `preset_payload` | JSON — fixed `input_payload` fields this template forces |
| `credit_cost_override` | nullable — if set, wins outright over any computed cost |
| `is_active` | |

**`generation_jobs`** gets one new column: `credit_cost` (nullable int) — see
Section 3, "why the cost is locked in at submission time."

**Spec A's `tools.default_model_id`** gets its FK constraint added here
(pointing at `ai_models.model_id`, which now exists) if Spec A shipped first
without it.

## Section 3 — The pricing engine

New `app/core/pricing.py`, `resolve_credit_cost(db, feature_type, input_payload) -> int`:

```
1. input_payload names a template_id whose credit_cost_override is set?
   → return it. Done.
2. Otherwise: model_id = input_payload.get("model_id") or tool.default_model_id
   base = ai_models[model_id].base_credit_cost if model_id else tool.credit_cost
   → if model_id was resolved: apply THIS TOOL's own modifier logic, reading
     tool.pricing_config (e.g. resolution_multipliers) against input_payload
   → final cost
3. A tool with no default_model_id and no model_id in the request has no
   model concept at all → tool.credit_cost is the answer directly, no
   modifiers applied. This is every tool that exists today (Spec A's flat
   fallback keeps working unchanged).
```

Each tool's own modifier logic (e.g. "what does 4K mean for THIS tool") stays
in that tool's own file in `app/tools/` — `resolve_credit_cost` calls a small
optional `cost_modifier_fn` on `ToolSpec` if the tool defines one, otherwise
skips straight to the base cost. **This does not change "one file per tool,
self-contained"** — a tool that needs custom pricing logic writes it once, in
its own file, same as it would write its own request-shaping/response-parsing
logic per BOOK.md Ch. 12.

**Why the cost is computed once, at submission, and stored on the job — not
recomputed at completion:** `generation_controller.run_generation` calls
`resolve_credit_cost(...)` and writes the result to the new
`GenerationJob.credit_cost` column before enqueueing. `app/worker.py` deducts
exactly that stored number on success — never recomputes. This guarantees a
job's price can't drift if an admin edits `pricing_config`/`base_credit_cost`
mid-flight, and gives every ledger row (`reference_id` = job id) a precise,
permanent record of what that specific job actually cost.

## Section 4 — Credit refills, decoupled from provider billing cadence

Razorpay only charges a yearly subscription once a year — its
`subscription.charged` webhook cannot drive a monthly refill for an annual
plan. So refills are **not** driven by provider webhooks at all. A new **arq
cron job** (arq already supports scheduled jobs — same process as
`app/worker.py`, no new infrastructure) runs daily:

```python
async def refill_due_credits(ctx):
    db = SessionLocal()
    try:
        due = db.query(TeamSubscription).filter(
            TeamSubscription.next_credit_refill_at <= datetime.utcnow(),
            TeamSubscription.status.in_(["active", "free"]),
        ).all()
        for sub in due:
            plan = db.get(Plan, sub.plan_id)
            _grant_credits(db, sub.team_id, plan.credit_allowance, reason="plan_grant")
            sub.next_credit_refill_at += relativedelta(months=1)
        db.commit()
    finally:
        db.close()
```

Applies **uniformly to every team** — Free, monthly-paid, yearly-paid — one
mechanism, no special cases. `WorkerSettings.cron_jobs` gains this entry.

Provider webhooks (`subscription.charged/cancelled/halted`) answer a
different question — "is this subscription currently paid for" — and only
update `team_subscriptions.status`/`current_period_end`. The two concerns
never share code.

## Section 5 — Enforcement points

- **`generation_controller.run_generation` / `run_generation_bulk`**: resolve
  cost, check `team_credit_balances.balance >= cost` → 402 if short, before
  creating the job.
- **`app/worker.py`, `_poll` (on success only, per the earlier decision)**:
  deduct `job.credit_cost`, write the `credit_transactions` row
  (`reason='generation_spend'`, `reference_id=job.id`), update the balance.
  A **failed** job never costs anything.
- **`team_controller.add_member`**: check current member count against the
  team's plan's `max_team_members` → 403 with an "upgrade your plan" message.
- **`team_controller.create_personal_team`** (Spec A): one new line —
  assign the Free plan, create the `team_subscriptions` row with
  `next_credit_refill_at = now`, and let the very next cron tick grant the
  starter credits (simplest correct option — avoids duplicating the grant
  logic that already exists in the cron job).

## Section 6 — Payment failure handling

Razorpay retries a failed recurring charge automatically for a few days
(its own dunning) — the team keeps working normally during that window
(`status` stays `'active'` or moves to `'past_due'`, still treated as usable).
Only when Razorpay's webhook reports the subscription `halted` does the team
get moved to the Free plan — not locked out, just back to free-tier limits
and allowance. No new grace-period timer needed on our side; Razorpay's own
retry cadence **is** the grace period.

## Section 7 — Routes

| Route | Does |
|---|---|
| `POST /billing/subscribe` | `{team_id, plan_id}` → `payment_provider.create_subscription(...)` → returns a checkout URL |
| `POST /billing/topup` | `{team_id, credit_pack_id}` → `payment_provider.create_one_time_order(...)` |
| `POST /billing/webhook/{provider}` | Signature-verified via `payment_provider.verify_webhook_signature`, **no session cookie** — the provider calls this directly. Processes charge/cancel/halt/payment-failed events |
| `GET /billing/teams/{id}` | Current plan, balance, subscription status, recent `credit_transactions` — for the console/future frontend |

Test console: new section — subscribe (redirect to the returned checkout
URL), a balance/plan display (calls `GET /billing/teams/{id}`), a manual
webhook-event simulator for local testing (since real Razorpay webhooks need
a publicly reachable URL — documented in DESIGN.md as needing ngrok or
similar for genuine end-to-end local testing).

## Documentation updates required (BOOK.md, append-only)

- New **Chapter 17 — Billing, Credits, and Dynamic Pricing**, following the
  existing chapter shape (problem → how it works → files → what it replaced,
  though nothing here replaces anything — it's all new).
- **Chapter 11** (AI Provider) gets a cross-reference note: the
  `PaymentProvider` seam in Section 1 above follows the identical pattern
  documented there — not a new idea, the second application of the same one.
- **Timeline**: one new entry.
- **Appendix A**: every new file (`core/payment_provider.py`, `core/pricing.py`,
  new models, new routes/controllers).
- **Appendix B**: the four new billing routes.
- **Appendix C** (Glossary): `credit_transactions` ledger pattern, "resolve
  cost at submission not completion."
- `.env.example` / `README.md` / `DESIGN.md`: Razorpay keys, the two new
  processes-adjacent facts (the refill cron needs the worker running; webhooks
  need a reachable URL).

## Verification plan

1. New team → `GET /billing/teams/{id}` shows Free plan, starter balance
   after one cron tick.
2. `/generate` on a team at zero balance → 402.
3. A successful job deducts exactly its stored `credit_cost`; a failed job
   deducts nothing; both show correctly in `credit_transactions`.
4. Change `tools.pricing_config` mid-flight on an in-progress job → confirm
   the job still deducts its originally-resolved cost, not a recomputed one.
5. Simulate a yearly subscription in a test DB with `next_credit_refill_at`
   forced into the past → cron grants credits without any Razorpay event
   firing.
6. Invite past a plan's `max_team_members` → 403.
7. A Razorpay test-mode webhook (`subscription.halted`) → team lands back on
   Free plan; balance/allowance reflect the Free plan going forward.
8. A template with `credit_cost_override` set always wins regardless of what
   model/settings are also present in `input_payload`.

## Non-goals (this spec)

- Actual pricing/plan values — `plans` ships with one placeholder Free plan;
  real tiers are populated whenever business decides them, no code change
  needed either way.
- A real admin UI for managing plans/models/templates — DB rows for now,
  same as `tools.credit_cost`/`is_active` in Spec A.
- Proration on mid-cycle plan upgrade/downgrade — first version treats a plan
  change as taking effect at the next renewal; proration is a real feature,
  deliberately deferred rather than guessed at.
- Invoicing/tax handling — `payments` is a reconciliation record, not a
  compliant invoice; revisit if/when that's a real requirement.
- A second `PaymentProvider` (Stripe/PayPal) — the seam is built for it,
  nothing implements it yet.
