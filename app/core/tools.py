"""The feature_type -> tool dispatch table. Every tool (23 of them,
eventually — UGC, on-model shots, photoshoot, ...) gets one ToolSpec here.
This is the seam the rest of the pipeline was built around: app/worker.py
looks a job's feature_type up in TOOLS to find which AIProvider instance
actually handles it, instead of going through one hardcoded global
provider. Different tools can point at different providers (e.g. a UGC
video tool on fal.ai, a photoshoot tool on Segmind) without touching
worker.py, generation_controller.py, or the schemas at all — add a
provider adapter, add a ToolSpec entry, done.

Every entry below points at the same MockAIProvider for now — there's no
real provider adapter yet (see core/ai_provider.py) — but the dispatch
mechanism itself is real and already exercised by app/worker.py and
scripts/test_pipeline.py.
"""

from dataclasses import dataclass

from app.core.ai_provider import AIProvider, ai_provider


@dataclass(frozen=True)
class ToolSpec:
    feature_type: str
    display_name: str
    output_media_type: str  # "image" | "video" — what this tool is expected
    # to produce. Not enforced against the provider's actual result yet
    # (there's only one mock, always "image") — becomes a real sanity check
    # once a video-capable provider exists: worker.py can flag a mismatch
    # instead of silently accepting whatever the provider returns.
    provider: AIProvider  # which AIProvider instance runs this tool. Several
    # ToolSpecs can share one instance (e.g. multiple tools on the same
    # aggregator account) or each get their own — the registry doesn't care.


TOOLS: dict[str, ToolSpec] = {
    "on_model_shots": ToolSpec(
        feature_type="on_model_shots",
        display_name="On-Model Shots",
        output_media_type="image",
        provider=ai_provider,
    ),
    "ugc": ToolSpec(
        feature_type="ugc",
        display_name="UGC Video",
        output_media_type="video",
        provider=ai_provider,
    ),
}


def get_tool(feature_type: str) -> ToolSpec | None:
    return TOOLS.get(feature_type)


def known_feature_types() -> list[str]:
    return sorted(TOOLS.keys())
