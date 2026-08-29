"""load_tool_config() — the DB-row-else-JSON-file loader shared by every
tool that keeps its models/prompts out of code (on_model_shots.py,
catalog_photoshoot.py — see docs/superpowers/specs/2026-08-29-*.md). Whole-
blob fallback: if the DB row for this feature_type doesn't exist, or the
DB isn't reachable at all, the checked-in JSON file is used in full — no
per-key merging."""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.tool_config import ToolConfig


def load_tool_config(db: Session, feature_type: str, fallback_path: Path) -> dict:
    try:
        row = db.get(ToolConfig, feature_type)
        if row and row.config_json:
            return row.config_json
    except Exception:
        pass  # DB unreachable — same crash-tolerance philosophy as
              # main.py's startup tool-sync (app/tools/sync.py)
    return json.loads(fallback_path.read_text(encoding="utf-8"))
