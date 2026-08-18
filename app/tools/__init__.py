"""Importing this package registers every tool below into the shared
registry (app/tools/registry.py) — this is the only import app/worker.py
and app/schemas/generation.py need; neither imports an individual tool
module directly. Add a new tool by adding one file here (see
on_model_shots.py for the pattern) and importing it below — nothing else
in the app changes.
"""

from app.tools import on_model_shots as _on_model_shots  # noqa: F401
from app.tools import ugc as _ugc  # noqa: F401

from app.tools.registry import TOOLS, ToolSpec, get_tool, known_feature_types  # noqa: F401
