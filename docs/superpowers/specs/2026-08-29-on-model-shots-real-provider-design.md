# On-Model Shots — real fal.ai provider, DB-backed models/prompts

**Status:** Ready for review
**Depends on:** nothing (touches only `on_model_shots`'s own files + one new table)
**Depended on by:** nothing yet — the other 22 tools stay on `MockAIProvider`

## Why

`on_model_shots` is currently a 20-line stub routed to `MockAIProvider`
(`app/tools/on_model_shots.py`). A working standalone version of the real
flow already exists (`flow.py` / `streamlit_app.py`, verified against real
fal.ai calls) but lives outside the backend, with every model id and system
prompt hardcoded in Python/`.env`. This spec ports that flow into the
backend as the tool's real provider, and moves its 4 model ids + 3 system
prompts out of code into a DB row an admin can edit from the CMS — with a
checked-in JSON file as the fallback/seed when no DB is reachable yet (e.g.
a fresh laptop), so the same feature works before and after a DB exists.

Scoped **only** to `on_model_shots`. No other tool, and no app-wide config
system, is touched.

## Architecture — how a shoot maps onto the existing job system

The existing job model is one job → one input asset → one output asset
(`AIProvider.submit(feature_type, source_asset_url, input_payload)`,
`GenerationJob.output_asset_id`). A shoot needs several input images (model
+ garment(s) + optional references) and produces up to 4 output images
(one per pose). Rather than changing that contract, a shoot is split into
three steps, only the last of which touches the job/worker pipeline at all:

```
1. POST /teams/{id}/on-model-shots/model-image   → resolves model image, returns an Asset
2. POST /teams/{id}/on-model-shots/prompts       → assembles images, VLM writes N pose prompts, safety pre-check
3. POST /teams/{id}/generate  ×N (existing route)  → one ordinary job per pose, feature_type="on_model_shots"
```

Steps 1–2 are synchronous controller calls (LLM calls only, seconds — no
image-gen wait in step 2, one image-gen call in step 1's "generate" mode).
Step 3 is the **existing, unmodified** `/generate` endpoint, worker,
`GenerationJob` table, and credit charging — called once per prompt
returned by step 2. **Nothing in `worker.py`, `AIProvider`'s interface,
`generation_controller.py`, or the job table changes.**

### Rule: only outputs get stored; fal URLs are never the permanent one

fal's result URLs expire (confirmed — see `flow.py`'s `download_image`
docstring). Every image fal.ai *generates* is downloaded and re-saved
through the existing `storage` seam (`app/core/storage.py` — local disk
today via `STORAGE_ROOT_DIR`, swappable to cloud storage later, no new
abstraction) **before** it is ever handed back as an `Asset.url`:

- Model-image "generate" candidates (step 1) → saved as a real `Asset`
  immediately, every attempt, clean or flagged.
- Final per-pose outputs (step 3) → `FalOnModelProvider.poll_result()`
  downloads the finished image's bytes and returns them as
  `GenerationResult.content`; `worker.py`'s existing `_poll()` already does
  `storage.save(...)` + creates the `Asset` from that — **zero changes
  needed there**, it's already built this way (see `MockAIProvider`).

Garment/reference images going *in* are never re-stored by this feature —
they're either an `Asset` the user already uploaded (its URL was stored at
*that* upload) or a plain URL, read once by fal and otherwise untouched. No
new DB rows are created for inputs.

## New files

| File | Purpose |
|---|---|
| `app/tools/on_model_shots.py` | Grows from the registration stub into the real port of `flow.py`: model resolution, both safety layers, `assemble_inputs`, router + VLM pose-prompt writing, `build_image_size`/`validate_custom_size`, config loader. All on-model-shots-specific knowledge lives here. |
| `app/core/fal_provider.py` | `class FalOnModelProvider(AIProvider)` — generic async submit/poll against fal's `submit`/`status`/`result` API. Knows nothing about poses/prompts/safety; just runs one `image_urls + prompt + image_size → image` call. Named generically since a future tool could reuse it. |
| `app/models/tool_config.py` | New `ToolConfig` table (below). |
| `app/schemas/on_model_shots.py` | Request/response models for the two new endpoints. |
| `app/controllers/on_model_shots_controller.py` | Steps 1–2's logic. |
| `app/routes/on_model_shots_routes.py` | Steps 1–2's routes, registered in `main.py` like every other router. |
| `app/tools/on_model_shots_config.json` | Checked-in seed/fallback — today's confirmed model ids + all 3 system prompts + model presets. This is the file you copy to another laptop. |
| `alembic/versions/xxxx_add_tool_config_table.py` | Creates `tool_config`. |

`requirements.txt` gains `fal-client`. `flow.py`'s use of `requests` becomes
`httpx` (already a dependency) — no new HTTP library.

## DB-backed models + prompts, JSON fallback

One new table, deliberately generic in shape (keyed by `feature_type`) even
though only `on_model_shots` gets a row today:

```python
class ToolConfig(Base):
    __tablename__ = "tool_config"
    feature_type = Column(String, primary_key=True)   # "on_model_shots"
    config_json = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
```

Registered in `app/core/cms_registry.py` (`config_json` as a `kind="json"`
field) — same generic CRUD the CMS already gives `AIModel`/`Tool`, no new
admin UI code needed.

`config_json` shape (mirrors `flow.py`'s `MODEL_CONFIG` + system prompts +
`MODEL_LIBRARY`):

```json
{
  "models": {
    "final_generation": "fal-ai/bytedance/seedream/v4.5/edit",
    "text_to_image": "fal-ai/bytedance/seedream/v4.5/text-to-image",
    "prompt_writer": "google/gemini-3.1-pro-preview",
    "safety_check": "google/gemini-2.5-flash"
  },
  "prompts": {
    "model_prompt_writer": "...",
    "description_safety": "...",
    "image_nsfw": "...",
    "general": "...",
    "intimate": "...",
    "local_safety_check": "..."
  },
  "presets": { "preset_1": "https://.../preset_1.jpg", "preset_2": "..." }
}
```

`app/tools/on_model_shots_config.json` holds the identical shape, seeded
with the values you confirmed (the model block above, and the current
`PROMPT_WRITER_SYSTEM_GENERAL`/`_INTIMATE`/etc. text from `flow.py`).

Loader, in `app/tools/on_model_shots.py`:

```python
def get_config(db: Session) -> dict:
    try:
        row = db.get(ToolConfig, "on_model_shots")
        if row and row.config_json:
            return row.config_json
    except Exception:
        pass  # DB unreachable — same crash-tolerance philosophy as
              # main.py's startup tool-sync
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
```

Whole-blob fallback (not per-key merge): if the DB row doesn't exist, or
the DB isn't reachable, the JSON file is used in full. `FAL_KEY` stays in
`.env` — it's a secret, not config, and isn't part of this table.

Controllers (steps 1–2) already have a `db` session via `Depends(get_db)`
and call `get_config(db)` directly. `FalOnModelProvider` (step 3) has no
`db` param on the `AIProvider` interface, so it opens its own short-lived
`SessionLocal()` to read config — same pattern `worker.py`'s `_submit`/
`_poll` already use.

## Step 1 — model image

`POST /teams/{team_id}/on-model-shots/model-image`

```python
class ModelImageResolveRequest(BaseModel):
    mode: Literal["generate", "upload", "default"]
    # generate:
    gender: str | None = None
    age_bracket: str | None = None
    skin_tone: str | None = None
    body_type: str | None = None
    additional_notes: str = ""
    # upload: an Asset the caller already created via POST /teams/{id}/assets
    asset_id: str | None = None
    # default:
    preset_id: str | None = None

class ModelImageResolveResponse(BaseModel):
    asset_id: str | None   # null only for "default" — see below
    url: str
    clean: bool
    reason: str | None
    description: str | None   # "generate" only — the LLM-written prompt text
```

- **generate**: ports `generate_model_candidate` — LLM writes the
  description, both text-safety layers run (keyword blocklist raises 400
  immediately; the LLM check returns a normal 400 with its reason, same as
  `flow.py`'s `ValueError`), then one text-to-image call, then the image
  NSFW check. **A new `Asset` (kind="generated") is created every call,
  clean or flagged** — same "always show it, let the human override an
  obvious false positive" philosophy as `streamlit_app.py`. Regenerate is
  just calling this again; there's no separate "approve" endpoint, the
  frontend just remembers which `asset_id` it liked. No credit charge for
  this step (see Known gaps).
- **upload**: `asset_id` must belong to the caller's team (same ownership
  check `generation_controller._resolve_and_check_credits` already does
  for `source_asset_id`). Runs `check_image_nsfw` against that asset's
  existing `url` — no new `Asset` created, reuses it. Not clean → 400
  (matches `flow.py`: an upload can't be regenerated, caller uploads a
  different file and calls again).
- **default**: looks up `preset_id` in `config["presets"]`. No `Asset`
  exists for a preset (it's a static, shared, pre-vetted URL, not
  team-owned) — `asset_id` is `null` in the response, and step 3 leaves
  `GenerationJob.source_asset_id` null for this path, passing the preset
  URL directly inside `input_payload` instead.

## Step 2 — prompts

`POST /teams/{team_id}/on-model-shots/prompts`

```python
class PromptsRequest(BaseModel):
    model_image_url: str          # from step 1's response
    garment_asset_ids: list[str]  # already-uploaded Assets, this team
    reference_asset_ids: list[str] = []
    garment_type: str = "bra"
    num_poses: int = 4
    user_prompt: str | None = None
    resolution_mode: str = "standard"
    aspect_ratio: str = "3:4"
    custom_width: int | None = None
    custom_height: int | None = None

class PromptsResponse(BaseModel):
    prompts: list[str]
    image_urls: list[str]
    labels: list[str]
    image_size: dict | str    # resolved once here via build_image_size,
                               # so FalOnModelProvider never has to know
                               # about aspect-ratio semantics
```

Ports `assemble_inputs` (≤10 check → 400 naming how many to trim, same as
`flow.py`), the intimate/general router, one VLM call for N distinct pose
prompts (or the fidelity-guardrail-wrapped `user_prompt` repeated N times,
unchanged from `flow.py`'s behavior), then `run_local_safety_check` — not
clean → 400 with its reason. `garment_asset_ids`/`reference_asset_ids` are
resolved to URLs via a normal `db.get(Asset, ...)` + team check, same
pattern as `asset_controller`.

## Step 3 — generation (existing, unmodified `/generate`)

Frontend calls the existing endpoint once per prompt from step 2:

```json
{
  "team_id": "...",
  "feature_type": "on_model_shots",
  "source_asset_id": "<model asset id, or omitted for a preset>",
  "input_payload": {
    "prompt": "<one pose prompt>",
    "image_urls": [...],
    "labels": [...],
    "image_size": {...or "portrait_4_3" etc.},
    "model_image_url": "<only used when source_asset_id is omitted, i.e. preset mode>"
  }
}
```

`FalOnModelProvider.submit()`:
1. Opens a `SessionLocal()`, reads `config["models"]["final_generation"]`.
2. Calls `fal_client.submit(model, arguments={prompt, image_urls, image_size, num_images: 1, max_images: 1, enable_safety_checker: True})` — fal's real async submit call (not the blocking `.subscribe()` `flow.py`'s tester uses), returns a `request_id` immediately.
3. Returns `GenerationHandle(external_job_id=f"{model}::{request_id}", provider="fal")` — the model id is embedded so a poll landing on a different worker process later still knows which fal application to ask.

`FalOnModelProvider.poll_result(handle)`:
1. Splits `handle.external_job_id` back into `model, request_id`.
2. Calls fal's status check; not done → raise `GenerationPending` (worker
   requeues via `Retry`, unchanged).
3. Done → fetches the result, **downloads the image bytes** (`httpx.get`
   on the result URL), returns `GenerationResult(media_type="image", content=<bytes>, extension=<guessed from the URL/content-type, same `_guess_extension`-style logic `worker.py` already has for product imports>)`. `worker.py` takes it from there exactly as it does for `MockAIProvider` today.
4. fal reports failure → raise `GenerationFailed(<its message>)`.

## Safety gates — preserved exactly

Every gate from `flow.py` carries over unchanged: keyword blocklist on the
description (step 1), LLM description check (step 1), image NSFW check
(step 1, both generate and upload paths), local safety pre-check on the
assembled prompts+images (step 2), and `enable_safety_checker: True` on
the final generation call itself (step 3) as the independent backstop. No
gate is removed, loosened, or reordered from the working version.

## Known gaps (explicitly out of scope for this pass)

- **No credit charge for step 1** (model-image generate/regenerate) — only
  the per-pose `/generate` call in step 3 costs credits, via the existing,
  unmodified mechanism. Easy to add a flat cost to step 1 later if wanted.
- **Local storage URLs must be publicly reachable for fal to fetch them**
  (garment/reference/model images passed as `image_urls`). Fine in
  production behind a real `BACKEND_URL`; on `localhost` fal cannot reach
  them — same class of gap `docs/BOOK.md` already lists for cloud storage,
  not solved here.
- Presets (`config["presets"]`) are plain URLs the admin edits into
  `ToolConfig`/the JSON fallback directly — no upload UI for adding a new
  preset image in this pass.

## Testing

Extends the existing manual-verification style (`scripts/test_pipeline.py`)
with a script exercising steps 1→2→3 against real fal.ai calls, mirroring
what `streamlit_app.py` already proves interactively. No automated test
suite exists for generation yet project-wide (documented gap in
`docs/BOOK.md`) — not introduced here either, consistent with the rest of
the codebase.
