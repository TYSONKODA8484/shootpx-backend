"""catalog_photoshoot_controller — the one pre-step endpoint's controller
logic. fal/VLM calls are monkeypatched at the app.tools.catalog_photoshoot
module boundary."""

import pytest
from fastapi import HTTPException

from app.controllers import catalog_photoshoot_controller as controller
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import Team, TeamMembership, new_id
from app.models.user import User
from app.schemas.catalog_photoshoot import CatalogShotsRequest
from app.tools import catalog_photoshoot as tool

_FAKE_CONFIG = {
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
    monkeypatch.setattr(tool, "get_config", lambda db: _FAKE_CONFIG)


def test_build_shots_rejects_asset_from_another_team(db_session):
    team, user = _make_team_and_user(db_session)
    other_team, other_user = _make_team_and_user(db_session)
    other_asset = _make_asset(db_session, other_team, other_user)

    payload = CatalogShotsRequest(product_asset_ids=[other_asset.id])
    with pytest.raises(HTTPException) as exc_info:
        controller.build_shots(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400


def test_build_shots_blocked_by_safety_check(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    product = _make_asset(db_session, team, user)
    monkeypatch.setattr(tool, "run_safety_check", lambda *a, **k: (False, "explicit content"))

    payload = CatalogShotsRequest(product_asset_ids=[product.id])
    with pytest.raises(HTTPException) as exc_info:
        controller.build_shots(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400
    assert "explicit content" in exc_info.value.detail


def test_build_shots_returns_prompts_and_resolved_image_size(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    product = _make_asset(db_session, team, user, url="https://x/shoe.jpg")
    monkeypatch.setattr(tool, "run_safety_check", lambda *a, **k: (True, ""))
    monkeypatch.setattr(tool, "build_shot_prompts", lambda *a, **k: ["shot1", "shot2"])

    payload = CatalogShotsRequest(product_asset_ids=[product.id], num_outputs=2, aspect_ratio="1:1")
    result = controller.build_shots(db_session, team.id, user, payload)

    assert result.prompts == ["shot1", "shot2"]
    assert result.image_urls == ["https://x/shoe.jpg"]
    assert result.image_size == "square_hd"
