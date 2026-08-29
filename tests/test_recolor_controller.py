"""recolor_controller — the one pre-step endpoint's controller logic.
Reuses catalog_photoshoot's run_safety_check CODE directly (monkeypatched
at that module's boundary), but always with recolor's OWN config."""

import io

import pytest
from fastapi import HTTPException
from PIL import Image

from app.controllers import recolor_controller as controller
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import Team, TeamMembership, new_id
from app.models.user import User
from app.schemas.recolor import RecolorPromptRequest
from app.tools import catalog_photoshoot as catalog_tool
from app.tools import recolor as tool

_FAKE_CONFIG = {
    "models": {"recolor_generation": "m", "prompt_writer": "m", "safety_check": "m"},
    "prompts": {"preservation_instructions": "PRESERVE.", "recolor_target_writer": "s", "safety_check": "s"},
}


def _make_team_and_user(db, role="owner"):
    team = Team(id=new_id(), name="Test Team")
    user = User(id=new_id(), email=f"{new_id()}@example.com")
    db.add_all([team, user])
    db.commit()
    db.add(TeamMembership(id=new_id(), team_id=team.id, user_id=user.id, role=role))
    db.commit()
    return team, user


def _make_asset(db, team, user, url="https://x/photo.jpg"):
    asset = Asset(
        team_id=team.id, created_by=user.id, kind=AssetKind.upload.value,
        media_type=MediaType.image.value, storage_key=f"{team.id}/{new_id()}.jpg", url=url,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _image_bytes(width=1024, height=768):
    img = Image.new("RGB", (width, height), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    monkeypatch.setattr(tool, "get_config", lambda db: _FAKE_CONFIG)


def test_build_prompt_rejects_asset_from_another_team(db_session):
    team, user = _make_team_and_user(db_session)
    other_team, other_user = _make_team_and_user(db_session)
    other_asset = _make_asset(db_session, other_team, other_user)

    payload = RecolorPromptRequest(image_asset_ids=[other_asset.id], color="#FF0000", description="the shirt")
    with pytest.raises(HTTPException) as exc_info:
        controller.build_prompt(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400


def test_build_prompt_blocked_by_safety_check(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    photo = _make_asset(db_session, team, user)
    monkeypatch.setattr(catalog_tool, "run_safety_check", lambda *a, **k: (False, "explicit content"))

    payload = RecolorPromptRequest(image_asset_ids=[photo.id], color="#FF0000", description="the shirt")
    with pytest.raises(HTTPException) as exc_info:
        controller.build_prompt(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400
    assert "explicit content" in exc_info.value.detail


def test_build_prompt_auto_suggests_target_when_description_blank(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    photo = _make_asset(db_session, team, user)
    monkeypatch.setattr(catalog_tool, "run_safety_check", lambda *a, **k: (True, ""))
    monkeypatch.setattr(tool, "suggest_recolor_target", lambda *a, **k: "the jacket")

    payload = RecolorPromptRequest(image_asset_ids=[photo.id], color="#FF0000", resolution_mode="standard", aspect_ratio="1:1")
    result = controller.build_prompt(db_session, team.id, user, payload)

    assert result.description == "the jacket"
    assert "Change the jacket in #Image_1 to #FF0000" in result.prompt


def test_build_prompt_skips_suggestion_when_description_given(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    photo = _make_asset(db_session, team, user)
    monkeypatch.setattr(catalog_tool, "run_safety_check", lambda *a, **k: (True, ""))

    def _should_not_be_called(*a, **k):
        raise AssertionError("suggest_recolor_target must not run when a description is given")

    monkeypatch.setattr(tool, "suggest_recolor_target", _should_not_be_called)

    payload = RecolorPromptRequest(
        image_asset_ids=[photo.id], color="#00FF00", description="the sleeves",
        resolution_mode="standard", aspect_ratio="1:1",
    )
    result = controller.build_prompt(db_session, team.id, user, payload)
    assert result.description == "the sleeves"


def test_build_prompt_match_input_fetches_bytes_and_computes_size(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    photo = _make_asset(db_session, team, user, url="https://x/photo.jpg")
    monkeypatch.setattr(catalog_tool, "run_safety_check", lambda *a, **k: (True, ""))
    monkeypatch.setattr(controller.httpx, "get", lambda url, timeout=30.0: _FakeResponse(_image_bytes(1024, 768)))

    payload = RecolorPromptRequest(image_asset_ids=[photo.id], color="#FF0000", description="the shirt")  # default match_input
    result = controller.build_prompt(db_session, team.id, user, payload)

    assert result.image_size == {"width": 1024, "height": 768}


def test_build_prompt_standard_mode_uses_build_image_size(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    photo = _make_asset(db_session, team, user)
    monkeypatch.setattr(catalog_tool, "run_safety_check", lambda *a, **k: (True, ""))

    payload = RecolorPromptRequest(
        image_asset_ids=[photo.id], color="#FF0000", description="the shirt",
        resolution_mode="standard", aspect_ratio="3:4",
    )
    result = controller.build_prompt(db_session, team.id, user, payload)
    assert result.image_size == "portrait_4_3"
