"""COPY THIS FILE to add a new tool. Rename it, fill in the two blanks
below, then register it in app/tools/__init__.py (one import line) —
nothing else in the app changes. This file starts with `_` so it is never
itself imported/registered by __init__.py.

    1. cp app/tools/_template.py app/tools/<your_feature_type>.py
    2. Fill in feature_type / display_name / output_media_type / provider
       below (see the two patterns further down for `provider`).
    3. Add one line to app/tools/__init__.py:
           from app.tools import <your_feature_type> as _<your_feature_type>  # noqa: F401
    4. Done. POST /generate {"feature_type": "<your_feature_type>", ...}
       works immediately — no route, schema, or worker.py change needed.
"""

from app.core.ai_provider import ai_provider  # noqa: F401  (pattern A, below)
from app.tools.registry import ToolSpec, register

register(
    ToolSpec(
        feature_type="TODO_your_feature_type",  # the string clients pass in /generate
        display_name="TODO Human-Readable Name",
        output_media_type="image",  # or "video"
        provider=ai_provider,  # see the two patterns below
    )
)

# --- provider, pattern A: share an existing provider instance ---
# provider=ai_provider (as above) — fine when this tool has no per-tool
# request/response mapping to do yet (today, always true: everything is
# still MockAIProvider).

# --- provider, pattern B: this tool needs its own configured instance ---
# Once a real AIProvider adapter exists (e.g. FalProvider), a tool with
# its own model/payload shape gets its own configured instance, entirely
# in this file — nothing shared needs to change for that either:
#
#   from app.core.some_real_provider import FalProvider
#   provider = FalProvider(model_id="fal-ai/some-model", ...)
#   register(ToolSpec(..., provider=provider))
