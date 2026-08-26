"""tests/test_templates_catalog.py — GET /templates' filter/search/cost
logic."""

from app.controllers import template_controller
from app.models.template import Template
from app.models.team import new_id
from app.models.tool import Tool


def _tool(db, feature_type="product_photoshoot", credit_cost=1):
    tool = db.get(Tool, feature_type)
    if tool is None:
        tool = Tool(feature_type=feature_type, display_name=feature_type, output_media_type="image", credit_cost=credit_cost)
        db.add(tool)
        db.commit()
    return tool


def _template(db, *, name, category, feature_type, preset=None, credit_cost_override=None, is_active=True):
    tpl = Template(
        id=new_id(), name=name, category=category, feature_type=feature_type,
        preset_payload=preset or {}, credit_cost_override=credit_cost_override, is_active=is_active,
    )
    db.add(tpl)
    db.commit()
    return tpl


def test_list_templates_returns_total_and_rows(db_session):
    _tool(db_session)
    _template(db_session, name="Wet Stone Ledge", category="Photoshoot", feature_type="product_photoshoot")

    result = template_controller.list_templates(db_session)

    assert result.total == 1
    assert result.templates[0].name == "Wet Stone Ledge"


def test_list_templates_filters_by_category(db_session):
    _tool(db_session)
    _template(db_session, name="Wet Stone Ledge", category="Photoshoot", feature_type="product_photoshoot")
    _template(db_session, name="Apparel Tee Front", category="Mockup", feature_type="product_photoshoot")

    result = template_controller.list_templates(db_session, category="Mockup")

    assert result.total == 1
    assert result.templates[0].category == "Mockup"


def test_list_templates_search_is_case_insensitive_substring(db_session):
    _tool(db_session)
    _template(db_session, name="Wet Stone Ledge", category="Photoshoot", feature_type="product_photoshoot")
    _template(db_session, name="Marble Vanity", category="Photoshoot", feature_type="product_photoshoot")

    result = template_controller.list_templates(db_session, q="stone")

    assert result.total == 1
    assert result.templates[0].name == "Wet Stone Ledge"


def test_list_templates_credit_cost_uses_override_when_set(db_session):
    _tool(db_session, credit_cost=1)
    _template(db_session, name="Wet Stone Ledge", category="Photoshoot", feature_type="product_photoshoot", credit_cost_override=3)

    result = template_controller.list_templates(db_session)

    assert result.templates[0].credit_cost == 3


def test_list_templates_credit_cost_falls_back_to_tool_cost(db_session):
    _tool(db_session, credit_cost=4)
    _template(db_session, name="360 Orbit", category="Motion", feature_type="product_photoshoot")

    result = template_controller.list_templates(db_session)

    assert result.templates[0].credit_cost == 4


def test_list_templates_excludes_inactive(db_session):
    _tool(db_session)
    _template(db_session, name="Retired Preset", category="Photoshoot", feature_type="product_photoshoot", is_active=False)

    result = template_controller.list_templates(db_session)

    assert result.total == 0
