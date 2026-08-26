# Tool/Template Visibility — Backend Confirmation & Contract

Reply to `TOOL-VISIBILITY-ANSWERS.md`. Short version: **your plan is
correct, nothing on the backend blocks it — go build exactly what your
"actual ask, restated" section describes.** This doc is just the exact
contract to build against, confirmed live (not just read from code).

---

## Bottom line

No new endpoint, no new fields, no combined `/studio-config`, no
"coming soon" state. `GET /tools` and `GET /templates` already are the
complete mechanism:

1. Fetch `GET /tools` once when the Studio shell mounts.
2. Build a `Set` of the `feature_type`s it returns.
3. Filter/grey your existing hardcoded tiles (Tools page, Home strip,
   Refine tabs, Video tabs) against that set.
4. `GET /templates` already self-filters (`is_active`/`category`/`q`) —
   no change needed, keep calling it as you do today.

---

## `GET /tools`

No auth. Returns a **flat JSON array** (not wrapped in `{ total, ... }`),
one object per active tool:

```json
[
  { "feature_type": "magic_erase", "display_name": "Magic Erase", "output_media_type": "image", "credit_cost": 1 },
  { "feature_type": "product_motion", "display_name": "Product Motion", "output_media_type": "video", "credit_cost": 4 }
]
```

**Order is not guaranteed** — keep your own grouping/order (`TOOL_GROUPS`,
`REFINE_TOOLS`, `QUICK_TOOLS`), just filter against the set.

**Every `feature_type` live right now** (13 rows — 12 Studio tools + 1
that isn't a Studio tile):

| `feature_type` | `display_name` | `output_media_type` | `credit_cost` |
|---|---|---|---|
| `background_swap` | Background Swap | image | 1 |
| `flat_lay_angles` | Flat Lay / Angles | image | 1 |
| `inpaint` | Inpaint | image | 1 |
| `magic_erase` | Magic Erase | image | 1 |
| `mockup_studio` | Mockup Studio | image | 1 |
| `on_model_shots` | On-Model Shots | image | 1 |
| `product_motion` | Product Motion | video | 4 |
| `product_photoshoot` | Product Photoshoot | image | 1 |
| `relight_shadows` | Relight & Shadows | image | 1 |
| `resize_outpaint` | Resize & Outpaint | image | 1 |
| `ugc` | UGC Video | video | 1 |
| `upscale_4k` | Upscale 4K | image | 1 |
| `product_import` | Product Import (URL Pull) | **`product_data`** | 5 |

⚠️ **`product_import`** will show up in this list too — it's the "paste a
listing URL" feature, not a tile in the Tools/Refine/Video grids you
mapped. Its `output_media_type` is the literal string `"product_data"`,
not `"image"`/`"video"`. Since you're only matching against known tile
`feature_type`s anyway, this one just won't match anything and can be
ignored — flagging so it doesn't look like a bug if you log unmatched
entries.

This matches your tile inventory (§1 of your own doc) exactly: all 12
Studio-tool `feature_type`s are present; `inpaint` is here too even though
it currently has no Tools-page tile (Refine-tab only, as you noted).

---

## `GET /templates`

No auth. Query params: `category` (exact match), `q` (substring search on
`name`, case-insensitive), `limit` (default 20, max 100), `offset`
(default 0).

```json
{
  "total": 24,
  "templates": [
    {
      "id": "…", "name": "Wet Stone Ledge", "category": "Photoshoot",
      "feature_type": "product_photoshoot", "credit_cost": 1,
      "preview_asset_url": null,
      "input_payload_preset": { "prompt": "wet stone ledge, cold morning light", "aspect": "1:1", "mode": "creative" }
    }
  ]
}
```

24 rows seeded across 5 categories: `Photoshoot`, `Mockup`, `On-model`,
`Motion`, `UGC`. `preview_asset_url` is **`null` on every row right now** —
no real preview images exist yet. Render your own placeholder for `null`
rather than treating it as an error.

---

## Freshness — no propagation delay to plan around

Both endpoints hit Postgres directly on every call — zero caching layer,
zero delay. Confirmed live: toggled `magic_erase`'s `is_active` off via
the actual CMS (login → PATCH → checked `GET /tools`), it disappeared on
the very next call; flipped it back, it reappeared on the next call after
that. If a tile is ever stuck in the wrong state, it's a frontend
fetch-once-per-session caching thing on your side (per your own plan),
not backend staleness.

---

## Nothing else changes

- Two-state (`is_active`) only — no "coming soon" state exists or is
  planned unless you tell us you need it.
- No icon/description/category fields added to `Tool` — all of that stays
  frontend-owned, exactly as your doc recommended.
- No combined endpoint — keep `GET /tools` and `GET /templates` separate.

Go ahead and wire the filtering.
