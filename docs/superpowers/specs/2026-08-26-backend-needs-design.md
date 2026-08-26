# Backend Needs — Design Spec

Source request: `BACKEND-NEEDS.md` (repo root). This spec turns that request
document into concrete architecture decisions, in build order. Each phase
below is independently shippable and gets its own implementation-plan phase
downstream (via `writing-plans`); this doc is the shared reference so later
phases don't re-litigate decisions made here.

Once all phases ship, `BACKEND-NEEDS.md` is deleted (superseded by
`docs/BOOK.md` chapters written per phase) per its own closing note.

---

## Build order

1. Category A — 10 tool registrations
2. B1 — Asset Library (list + delete)
3. B2 — Activity Feed
4. B3 — Templates Catalog
5. B4 — Brand Kit
6. B5 — Export / Resize
7. B6 — Refine Version History
8. Cross-cutting cleanup (storage/, docs)

This mirrors `BACKEND-NEEDS.md`'s own stated priority order (cheapest/
highest-value first; B6 explicitly last since it has no data to show until
Category A tools have real usage chained via `source_asset_id`).

---

## Category A — 10 tool registrations

**New files**, each a ~10-line copy of `app/tools/on_model_shots.py`:

| file | `feature_type` | `output_media_type` | `credit_cost` |
|---|---|---|---|
| `product_photoshoot.py` | `product_photoshoot` | image | 1 |
| `background_swap.py` | `background_swap` | image | 1 |
| `mockup_studio.py` | `mockup_studio` | image | 1 |
| `flat_lay_angles.py` | `flat_lay_angles` | image | 1 |
| `magic_erase.py` | `magic_erase` | image | 1 |
| `inpaint.py` | `inpaint` | image | 1 |
| `relight_shadows.py` | `relight_shadows` | image | 1 |
| `upscale_4k.py` | `upscale_4k` | image | 1 |
| `resize_outpaint.py` | `resize_outpaint` | image | 1 |
| `product_motion.py` | `product_motion` | video | 4 |

Each: `register(ToolSpec(feature_type=..., display_name=..., output_media_type=..., provider=ai_provider))`.
Auto-discovered by `app/tools/__init__.py`'s `pkgutil` loop — no edit to that
file needed.

**Migration (data-only, new revision)**: pre-insert all 10 `tools` rows
directly via raw SQL, same shape as `3adad199e5b6_register_product_import...`:

```sql
INSERT INTO tools (feature_type, display_name, output_media_type, credit_cost, is_active, created_at, updated_at)
VALUES (:ft, :name, :media_type, :cost, true, now(), now())
```

Guarded by `SELECT 1 FROM tools WHERE feature_type = :ft` (skip if exists),
same idempotency as the existing migration. This is required because
`credit_cost` is DB-owned and defaults to `1` on first insert
(`sync_tools_to_db` never sets it) — without pre-seeding, `product_motion`
would silently start at 1 credit instead of 4 on first boot after the code
lands.

`input_payload` stays unvalidated (`dict[str, Any] = {}`, already the case in
`schemas/generation.py`) — no per-tool Pydantic shape yet, matching the
doc's explicit recommendation. Mask-based tools (`magic_erase`, `inpaint`)
send `mask_data_url` as a plain string key in that dict; no size limit
enforced yet (flagged as a future concern, not solved here).

`upscale_4k` PRO-gating: not implemented — no plan-gating system exists.

**No route/schema changes** — `/generate` and `/generate/bulk` already
validate `feature_type` against `known_feature_types()`.

---

## B1 — Asset Library

**`core/storage.py`**: add `delete(key: str) -> None` to the `Storage` ABC;
`LocalStorage.delete()` does `os.remove(path)`, catching and swallowing
`FileNotFoundError` (deleting an already-gone file is not an error here).

**`core/cache.py`**: `delete(namespace, key)` already exists — no change
needed (the source doc was wrong about this).

**`schemas/assets.py`**: add `AssetListOut { total: int, assets: list[AssetOut] }`.

**`asset_controller.py`** — two new functions:

- `list_assets(db, team_id, current_user, kind=None, media_type=None, limit=50, offset=0) -> AssetListOut`
  — `get_membership()` check, filter by optional `kind`/`media_type`, order
  `created_at desc`, `limit` capped at 200.
- `delete_asset(db, asset_id, current_user) -> None`
  — look up the `Asset`, 404 if missing (don't leak existence across teams —
  same pattern `get_membership` already uses); `get_membership(db, asset.team_id, ...)`
  then `can_upload_assets` check; `storage.delete(asset.storage_key)`;
  `cache.delete("media", asset.id)`; `db.delete(asset); db.commit()`.

`GenerationJob.output_asset_id` pointing at a deleted asset is left as-is —
no cascade delete of jobs (audit history stays intact; a 404'd image URL is
a frontend concern).

**`asset_routes.py`**: `GET /teams/{team_id}/assets`, `DELETE /assets/{asset_id}`
(204 on success).

---

## B2 — Activity Feed

**Option 1** (computed feed, no new table) — chosen per the doc's own
recommendation; revisit Option 2 (`activity_log` table) only if non-row-backed
events (team membership changes, brand kit edits) need to show up later.

**New files**: `schemas/activity.py`, `app/controllers/activity_controller.py`,
`app/routes/activity_routes.py` (own files — same reasoning `asset_routes.py`
already establishes: grouped by resource concept, not URL prefix).

`GET /teams/{team_id}/activity?limit=20&before=<iso-timestamp>`:

- Query `generation_jobs` where `status in (done, failed)`, `product_imports`
  where `status in (done, failed)`, and `credit_transactions` where `reason
  in (plan_grant, topup_purchase, subscription_cancelled)` — each filtered by
  `team_id` and (if `before` given) `created_at < before`, each capped at
  `limit` rows ordered `created_at desc`.
- Merge-sort the three lists in Python by `created_at desc`, take the first
  `limit`, and use the last item's `created_at` as `next_cursor` (`null` if
  fewer than `limit` results came back — no more pages).
- Synthetic per-kind ids: `"job:{id}"`, `"import:{id}"`, `"credit:{id}"` —
  keeps ids unique across the merged union without inventing a shared table.
- `title`/`detail` per kind:
  - job: title = `Tool.display_name` for `feature_type` (batch-fetched, one
    query for all distinct feature_types in the page); detail = `"Completed"`
    or `"Failed: {error}"`.
  - import: title = `product_name or source_url`; detail = status.
  - credit: title = `reason` (human-cased); detail = `f"{'+' if amount>0 else ''}{amount} credits"`.
- `asset_url`: for a job, the output asset's url (via `get_assets_cached`,
  same cache already used by `generation_controller._to_summaries`); for an
  import, its first scraped image; `null` for credit events.

---

## B3 — Templates Catalog

**Migration 1** (schema): add `name: String`, `category: String`,
`preview_asset_url: String, nullable=True` to `templates`.

**Migration 2** (data-only): seed ~24 rows spanning the 5 categories
(Photoshoot / Mockup / On-model / Motion / UGC), each with a real
`feature_type` (from Category A + existing `on_model_shots`/`ugc`) and a
`preset_payload` matching that tool's documented `input_payload` shape.
`preview_asset_url` seeded `null` — no real preview images exist yet;
seeding a fake URL would be dishonest data, `null` lets the frontend show its
own placeholder.

**New files**: `schemas/templates.py`, `template_controller.py`,
`template_routes.py`.

`GET /templates?category=&q=&limit=20&offset=0` — no auth (public catalog
data, same spirit as `GET /tools`). `q` does a simple `ILIKE` on `name`.
Returns `{ total, templates: [...] }`.

---

## B4 — Brand Kit

**New model file** `app/models/brand_kit.py`:

```python
class BrandKit(Base):
    __tablename__ = "brand_kits"
    id: str = new_id()
    team_id: str  # FK teams, UNIQUE
    palette: JSON  # list[str]
    heading_font: str | None
    body_font: str | None
    created_at, updated_at

class BrandMark(Base):
    __tablename__ = "brand_marks"
    id: str = new_id()
    brand_kit_id: str  # FK brand_kits
    asset_id: str       # FK assets
    variant: str         # free label, e.g. "light"/"dark"
    created_at
```

**Migration**: create both tables; add `assets.is_saved_product Boolean
default false`.

**New files**: `schemas/brand_kit.py`, `brand_kit_controller.py`,
`brand_kit_routes.py`.

- `GET /teams/{team_id}/brand-kit` — `get_or_create`: look up by `team_id`,
  create an empty row (`palette=[]`, fonts `null`) on first call, same
  lazy-default spirit as personal-team creation elsewhere in this codebase.
  Returns kit + its marks (joined).
- `PUT /teams/{team_id}/brand-kit` — full replace of `{palette, heading_font,
  body_font}`.
- `POST /teams/{team_id}/brand-kit/marks` — multipart upload; reuses
  `asset_controller.upload_asset()`'s save logic (factor the storage-write
  part into a small shared helper rather than duplicating it) to create the
  underlying `Asset(kind="upload")`, then inserts the `BrandMark` link row.
- `DELETE /brand-kit/marks/{mark_id}` — deletes only the `BrandMark` row, not
  the underlying `Asset` (that's a separate, explicit `DELETE /assets/{id}`
  from B1 if the user wants the file gone too — avoids a surprising cascade).
- `PATCH /assets/{asset_id}` (lives in `asset_controller.py`/`asset_routes.py`,
  not brand-kit's own files, since it's a general asset mutation) — body
  `{ is_saved_product: bool }`.

---

## B5 — Export / Resize

**Dependency**: add `Pillow` to `requirements.txt`.

**New file** `app/core/image_ops.py`:

```python
EXPORT_PRESETS = {
    "shopify_product": (2048, 2048, "JPEG"),
    "amazon_main":      (3000, 3000, "JPEG"),  # white-bg letterbox/pad
    "etsy_listing":     (2700, 2025, "JPEG"),
    "instagram_post":   (1080, 1350, "JPEG"),
    "master_png":       (4096, 4096, "PNG"),   # max-dimension, aspect preserved
}

def export_variant(source_bytes: bytes, preset_key: str) -> tuple[bytes, str]:
    """Resize + reformat via Pillow. Amazon's white-bg requirement is a
    plain white letterbox/pad, not real background removal (that's
    background_swap's job, a Category-A tool, not this function's)."""
```

**`Asset` model changes**: add nullable self-referential `source_asset_id`
(FK `assets.id`); extend the kind convention with `"exported"` (still a
plain string column, same as today — `AssetKind` enum gets an `exported`
member for code-side clarity, not enforced at the DB level any more strictly
than `kind` already is).

**Runs synchronously in the request** — not queued through arq. A Pillow
resize of a handful of presets is low-single-digit milliseconds; queuing it
would mean inventing a new job/poll shape for something that doesn't need
one. This is a deliberate simplification versus what the doc's endpoint
sketch implied.

**`CreditReason`**: add `export_spend`.

`POST /assets/{asset_id}/export` body `{ presets: [...] }`:
- membership + `can_upload_assets` check (reuse, per the doc).
- validate every requested preset key exists in `EXPORT_PRESETS` (400 if not).
- total cost = `1 * len(presets)` (your call: 1 credit per preset); check
  balance via `get_balance` (no "held credits" concept needed — synchronous,
  nothing in flight to race against); 402 if short.
- fetch source asset bytes (read from local disk via its `storage_key`),
  run `export_variant()` per preset, `storage.save()` each under
  `{team_id}/exports/{uuid}.{ext}`, create one `Asset(kind="exported",
  source_asset_id=original.id)` per preset.
- `apply_credit_delta(..., reason="export_spend", reference_id=original.id)`
  once for the total.
- Returns `{ exports: [ { preset, asset_id, url } ] }`.

---

## B6 — Refine Version History

**No new table.** New function in `asset_controller.py`:
`get_asset_versions(db, current_user, asset_id) -> VersionsOut`.

Walk: start at `asset_id` (after a membership check on its team). Look up
the most recent `GenerationJob` where `output_asset_id == current`. If
found: emit `{ asset_id: current, url, label: Tool.display_name for
job.feature_type, created_at: job.completed_at }`, then set
`current = job.source_asset_id` and repeat. If no such job exists (dead end)
or `current` is `None`: stop, emitting the final asset itself with
`label="Original"` and `created_at=asset.created_at`.

Naturally produces newest-first (starts at the given asset, walks backward).
`GET /assets/{asset_id}/versions` in `asset_routes.py`.

---

## Cross-cutting

- **`storage/` cleanup**: delete the contents of `storage/` (83 files,
  ~4.8MB at spec time) — confirmed with the user immediately before running
  it, even though pre-approved, since it's destructive. This does **not**
  touch DB rows; any `Asset` row pointing at a deleted file will 404 on its
  `url` until that row is separately removed via B1's `DELETE /assets/{id}`.
  No DB reset was requested.
- **Docs**: append one `docs/BOOK.md` chapter per shipped phase (matching
  its existing append-only style and chapter template), and extend
  `README.md`'s API-overview table, as each phase lands — not batched to
  the end.
- **`BACKEND-NEEDS.md`**: deleted once every phase above has shipped.

---

## Explicitly out of scope for this pass

- Real `AIProvider` adapters (everything still routes through
  `MockAIProvider`) — Category A is registrations only.
- Per-tool `input_payload` Pydantic validation.
- Plan-gating (`upscale_4k` PRO-only).
- `activity_log` table (Option 2) — only revisit if non-row-backed events
  need to appear in the feed.
- Cascading asset deletes onto `BrandMark`/`GenerationJob` rows that
  reference them.
