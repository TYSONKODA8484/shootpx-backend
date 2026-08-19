"""Importing this package registers every tool in this folder into the
shared registry (app/tools/registry.py) — this is the only import
app/worker.py and app/schemas/generation.py need; neither imports an
individual tool module directly.

Every module in this folder is imported automatically (auto-discovery, via
pkgutil below) — a new tool needs NO edit here. Add one by copying
_template.py to a new file (or a whole subpackage — see BOOK.md Chapter 12),
filling in its ToolSpec, and restarting the server. Modules prefixed `_`
(like _template.py) are skipped, same convention as everywhere else in this
codebase; `registry` is skipped explicitly since it's the registry itself,
not a tool.
"""

import importlib
import pkgutil
from pathlib import Path

_tools_dir = Path(__file__).parent
for _, _module_name, _ in pkgutil.iter_modules([str(_tools_dir)]):
    if _module_name.startswith("_") or _module_name == "registry" or _module_name == "sync":
        continue
    importlib.import_module(f"app.tools.{_module_name}")

from app.tools.registry import TOOLS, ToolSpec, get_tool, known_feature_types  # noqa: F401,E402
