"""creative_photoshoot_controller — the one pre-step endpoint's controller
logic. Reuses catalog_photoshoot's assemble/safety/build_image_size
directly (monkeypatched at that module's boundary), and
creative_photoshoot's own build_creative_prompt/apply_adult_floor."""

import pytest
from fastapi import HTTPException

from app.controllers import creative_photoshoot_controller as controller
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import Team, TeamMembership, new_id
from app.models.user import User
from app.schemas.creative_photoshoot import CreativePromptRequest
from app.tools import catalog_photoshoot as catalog_tool
from app.tools import creative_photoshoot as tool

_CREATIVE_CONFIG = {"models": {"prompt_writer": "m"}, "prompts": {"creative_prompt_writer": "s"}}
_CATALOG_CONFIG = {
    "models": {"catalog_generation": "m", "prompt_writer": "m", "safety_check": "m"},
    "prompts": {"shot_prompt_writer": "s", "safety_check": "s"},
}


def _make_team_and_user(db, role="owner"):
    team = Team(id=new_id(), name="Test Team")
    user = User(id=new_id(), email=f"{new_id()}@example.com")
    db.add_all([team, user])
    db.commit()
    db.add(TeamMembership(id=new_id(), team_id=team.id, user_id=user.id, role=role))
    db.commit()
    return team, user


def _make_asset(db, team, user, url="https://x/product.jpg"):
    asset = Asset(
        team_id=team.id, created_by=user.id, kind=AssetKind.upload.value,
        media_type=MediaType.image.value, storage_key=f"{team.id}/{new_id()}.jpg", url=url,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    monkeypatch.setattr(tool, "get_config", lambda db: _CREATIVE_CONFIG)
    monkeypatch.setattr(catalog_tool, "get_config", lambda db: _CATALOG_CONFIG)


def test_build_prompt_rejects_asset_from_another_team(db_session):
    team, user = _make_team_and_user(db_session)
    other_team, other_user = _make_team_and_user(db_session)
    other_asset = _make_asset(db_session, other_team, other_user)

    payload = CreativePromptRequest(product_asset_ids=[other_asset.id], user_prompt="a scene")
    with pytest.raises(HTTPException) as exc_info:
        controller.build_prompt(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400


def test_build_prompt_blocked_by_safety_check(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    product = _make_asset(db_session, team, user)
    monkeypatch.setattr(catalog_tool, "run_safety_check", lambda *a, **k: (False, "explicit content"))

    payload = CreativePromptRequest(product_asset_ids=[product.id], user_prompt="a scene")
    with pytest.raises(HTTPException) as exc_info:
        controller.build_prompt(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400
    assert "explicit content" in exc_info.value.detail


def test_build_prompt_rejects_when_neither_idea_nor_prompt(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    product = _make_asset(db_session, team, user)
    monkeypatch.setattr(catalog_tool, "run_safety_check", lambda *a, **k: (True, ""))

    payload = CreativePromptRequest(product_asset_ids=[product.id])
    with pytest.raises(HTTPException) as exc_info:
        controller.build_prompt(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400
    assert "Provide an idea, a prompt, or both" in exc_info.value.detail


def test_build_prompt_returns_final_prompt_with_adult_floor_applied(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    product = _make_asset(db_session, team, user, url="https://x/product.jpg")
    monkeypatch.setattr(catalog_tool, "run_safety_check", lambda *a, **k: (True, ""))

    payload = CreativePromptRequest(product_asset_ids=[product.id], user_prompt="on a beach", aspect_ratio="3:4")
    result = controller.build_prompt(db_session, team.id, user, payload)

    assert result.final_prompt.startswith("If this scene includes any person")
    assert result.final_prompt.endswith("on a beach")
    assert result.image_urls == ["https://x/product.jpg"]
    assert result.image_size == "portrait_4_3"
