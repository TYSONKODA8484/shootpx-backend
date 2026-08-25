from app.core.cms_registry import ENTITIES


def test_all_sixteen_entities_registered():
    assert len(ENTITIES) == 16


def test_tools_code_owned_fields_are_locked():
    """feature_type/display_name/output_media_type get silently overwritten
    by app/tools/sync.py's sync_tools_to_db on every boot (see
    app/models/tool.py's docstring) — editing them here would vanish on
    restart, so the CMS must never allow it."""
    tools = ENTITIES["tools"]
    locked = {f.name for f in tools.fields if not f.editable}
    assert {"feature_type", "display_name", "output_media_type"} <= locked
    assert tools.allow_create is False


def test_credit_transactions_is_create_only():
    ledger = ENTITIES["credit-transactions"]
    assert ledger.allow_update is False
    assert ledger.allow_delete is False
    assert ledger.allow_create is True


def test_every_entity_pk_field_exists_on_its_model():
    for config in ENTITIES.values():
        assert hasattr(config.model, config.pk_field), config.name
