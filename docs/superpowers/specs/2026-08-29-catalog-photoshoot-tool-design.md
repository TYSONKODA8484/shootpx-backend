# Catalog Photoshoot — new tool, real fal.ai provider

**Status:** Ready for review
**Depends on:** the on-model-shots spec (`2026-08-29-on-model-shots-real-provider-design.md`)
for shared mechanics — the `tool_config` table, `app/core/tool_config.py`'s
`load_tool_config()`, `FalImageEditProvider`, the "only outputs stored"
rule, and progressive per-job polling. This doc only covers what's
different.
**Depended on by:** nothing

## Why

A second, brand-new tool ported from a working standalone script
(`catalog_flow.py` / `catalog_streamlit_app.py`, verified against real
fal.ai calls) — genuinely simpler than on-model-shots: no model-selection
step, no intimate/general router, no per-category prompt split. N product
reference images in, N distinct catalog shots out, one VLM call decides
all N shots for whatever the product is. New `feature_type`, doesn't touch
`on_model_shots` or `product_photoshoot` (existing, unrelated stub).

## Architecture — reuses the on-model-shots pattern, minus a step

on-model-shots needed 3 steps because of the model-image sub-flow (its own
generate/upload/default/approve loop). Catalog has no such thing — product
images are just the caller's own already-uploaded assets — so it's 2 steps:

```
1. POST /teams/{id}/catalog-photoshoot/shots  → assembles product images, safety check, VLM writes N shot prompts
2. POST /teams/{id}/generate  ×N (existing route)  → one ordinary job per shot, feature_type="catalog_photoshoot"
```

Step 1 is synchronous (LLM calls only, no image-gen wait — same shape as
on-model-shots' step 2). Step 2 is the same existing, unmodified
`/generate` endpoint/worker/job table/credit charging, called once per
shot prompt. Same progressive-results behavior applies unchanged: the
frontend polls `GET /jobs?ids=...` and each shot appears the moment it's
done, sequential per user (per the shared lock addendum in the other
spec — already generic infrastructure once that lands, nothing further
needed here).

`GenerationJob.source_asset_id` is set to the **first** product asset (an
arbitrary but harmless pick, purely for `GET /assets/{id}/versions`
lineage) — all product images travel together in `input_payload` regardless,
same as garment/reference images do for on-model-shots.

## New files

| File | Purpose |
|---|---|
| `app/tools/catalog_photoshoot.py` | New tool registration (`ToolSpec(feature_type="catalog_photoshoot", ...)`) + the real port of `catalog_flow.py`: `assemble_product_images`, `run_safety_check`, `build_shot_prompts` (with its validate-and-retry-once behavior), `build_image_size` (catalog's own aspect-ratio/resolution rules — different constraints from on-model-shots', see `catalog_flow.py`'s section 2 notes: `auto_3K`, total-pixels-only custom-size check, auto-scale-not-reject), config loader. |
| `app/schemas/catalog_photoshoot.py` | Request/response models for the one new endpoint. |
| `app/controllers/catalog_photoshoot_controller.py` | Step 1's logic. |
| `app/routes/catalog_photoshoot_routes.py` | Step 1's route, registered in `main.py`. |
| `app/tools/catalog_photoshoot_config.json` | Checked-in seed/fallback — `CATALOG_GENERATION_MODEL` + `PROMPT_WRITER_MODEL` + `SAFETY_CHECK_MODEL` + the shot-prompt-writer and safety-check system prompts from `catalog_flow.py`. |

No new table, no new provider class, no `requirements.txt` change — all
reused from the on-model-shots work.

**`app/core/fal_provider.py`'s `FalImageEditProvider`** gets a second
instance, constructed the same way as on-model-shots' but pointed at a
different feature_type/config key:

```python
# app/tools/on_model_shots.py
provider = FalImageEditProvider(feature_type="on_model_shots", model_config_key="final_generation")

# app/tools/catalog_photoshoot.py
provider = FalImageEditProvider(feature_type="catalog_photoshoot", model_config_key="catalog_generation")
```

Same class, same submit/poll logic, each instance just reads a different
`tool_config` row and a different key inside it — this is the reuse the
on-model-shots spec's rename anticipated.

## DB config row

A second `tool_config` row, `feature_type="catalog_photoshoot"`:

```json
{
  "models": {
    "catalog_generation": "bytedance/seedream/v5/lite/edit",
    "prompt_writer": "google/gemini-3.1-pro-preview",
    "safety_check": "google/gemini-2.5-flash"
  },
  "prompts": {
    "shot_prompt_writer": "...",
    "safety_check": "..."
  }
}
```

Independent from `on_model_shots`'s row even though `prompt_writer` and
`safety_check` currently point at the same underlying models — each tool's
config can drift independently later (e.g. a cheaper/different safety
model for one tool only) without touching the other, which is the whole
point of keying `tool_config` by `feature_type`. Uses the same shared
`load_tool_config(db, "catalog_photoshoot", _CONFIG_PATH)` helper from
`app/core/tool_config.py` — no new loader logic, just a different
feature_type and a different fallback file.

## Step 1 — shots

`POST /teams/{team_id}/catalog-photoshoot/shots`

```python
class CatalogShotsRequest(BaseModel):
    product_asset_ids: list[str]   # already-uploaded Assets, this team, max 10
    num_outputs: int = 6
    resolution_mode: str = "standard"
    aspect_ratio: str = "1:1"
    custom_width: int | None = None
    custom_height: int | None = None
    user_prompt: str | None = None

class CatalogShotsResponse(BaseModel):
    prompts: list[str]
    image_urls: list[str]
    labels: list[str]
    image_size: dict | str
```

Ports, unchanged: the >10-images reject (400, names how many to trim),
`run_safety_check` (keyword check on `user_prompt` first, then one VLM
call folding "no minors" into the same nsfw check — not a separate step,
per `catalog_flow.py`'s explicit design note), `build_shot_prompts` (one
VLM call, validates exact-N/non-empty/no-duplicates, retries the VLM call
once before giving up — preserved exactly, since a bad shot list would
otherwise burn a real paid generation call per bad prompt to find out).
`product_asset_ids` resolved to URLs via `db.get(Asset, ...)` + team-
ownership check, same pattern as on-model-shots' garment images.

## Safety — preserved exactly

Same calibration as on-model-shots: flag only on a genuine, specific
reason to suspect a minor (never on youthfulness alone), ordinary product
photography — including apparel/underwear being worn, the product itself
— is not explicit on its own. `enable_safety_checker: True` stays on the
final generation call as the independent backstop, same as every other
tool using `FalImageEditProvider`.

## Known gaps (same as on-model-shots, not re-litigated)

- Local storage URLs must be publicly reachable for fal to fetch them —
  same production-vs-localhost caveat as the other spec.
- No credit charge beyond the existing per-job cost on step 2 — step 1 is
  free, same policy as on-model-shots' pre-steps.
