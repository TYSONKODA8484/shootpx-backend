"""app/core/tool_config.py's load_tool_config() — DB row first, checked-in
JSON file as the fallback when no row exists or the DB isn't reachable.
Whole-blob fallback, not per-key merging — see
docs/superpowers/specs/2026-08-29-on-model-shots-real-provider-design.md."""

import json

from app.core.tool_config import load_tool_config
from app.models.tool_config import ToolConfig


def test_load_tool_config_uses_db_row_when_present(db_session, tmp_path):
    db_session.add(ToolConfig(feature_type="on_model_shots", config_json={"models": {"a": "from-db"}}))
    db_session.commit()

    fallback = tmp_path / "fallback.json"
    fallback.write_text(json.dumps({"models": {"a": "from-json"}}))

    config = load_tool_config(db_session, "on_model_shots", fallback)
    assert config["models"]["a"] == "from-db"


def test_load_tool_config_falls_back_to_json_when_no_row(db_session, tmp_path):
    fallback = tmp_path / "fallback.json"
    fallback.write_text(json.dumps({"models": {"a": "from-json"}}))

    config = load_tool_config(db_session, "on_model_shots", fallback)
    assert config["models"]["a"] == "from-json"


def test_load_tool_config_falls_back_to_json_when_db_raises(monkeypatch, db_session, tmp_path):
    def _raise(*a, **k):
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(db_session, "get", _raise)
    fallback = tmp_path / "fallback.json"
    fallback.write_text(json.dumps({"models": {"a": "from-json"}}))

    config = load_tool_config(db_session, "on_model_shots", fallback)
    assert config["models"]["a"] == "from-json"
