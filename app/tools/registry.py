"""The registry every tool module in this package registers itself into.
Nothing here knows about any specific tool — see on_model_shots.py,
ugc.py, etc. for those. Callers outside this package (app/worker.py,
app/schemas/generation.py) import from app.tools (the package __init__,
which imports every tool module so they've all registered, then
re-exports this module's names), never from this file or an individual
tool module directly.
"""

from dataclasses import dataclass

from app.core.ai_provider import AIProvider


@dataclass(frozen=True)
class ToolSpec:
    feature_type: str
    display_name: str
    output_media_type: str  # "image" | "video" — what this tool is expected
    # to produce. Not cross-checked against the provider's actual result yet
    # (there's only ever been one mock result shape to check against) —
    # worth adding once a video-capable provider exists, so a misconfigured
    # tool fails loudly instead of quietly mislabeling an asset.
    provider: AIProvider  # which AIProvider instance runs this tool. Several
    # ToolSpecs can share one instance (e.g. multiple tools on the same
    # aggregator account) or each get their own.


TOOLS: dict[str, ToolSpec] = {}


def register(tool: ToolSpec) -> None:
    """Called once, at import time, by each tool's own module (see
    on_model_shots.py for the pattern). Errors loudly on a duplicate
    feature_type — two tools quietly fighting over the same dispatch key
    is exactly the kind of bug that should fail at startup, not at 2am
    when someone finally hits the wrong one."""
    if tool.feature_type in TOOLS:
        raise ValueError(
            f"feature_type {tool.feature_type!r} already registered "
            f"(by {TOOLS[tool.feature_type].display_name!r})"
        )
    TOOLS[tool.feature_type] = tool


def get_tool(feature_type: str) -> ToolSpec | None:
    return TOOLS.get(feature_type)


def known_feature_types() -> list[str]:
    return sorted(TOOLS.keys())
