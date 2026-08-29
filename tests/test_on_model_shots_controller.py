"""on_model_shots_controller — the two pre-step endpoints' controller
logic. fal/VLM calls are monkeypatched at the app.tools.on_model_shots
module boundary (same "isolate the controller, trust the seam" philosophy
as tests/test_asset_library.py's storage/cache monkeypatching)."""

import pytest
from fastapi import HTTPException

from app.controllers import on_model_shots_controller as controller
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import Team, TeamMembership, new_id
from app.models.user import User
from app.schemas.on_model_shots import ModelImageResolveRequest, PromptsRequest
from app.tools import on_model_shots as tool

_FAKE_CONFIG = {
    "models": {"final_generation": "m", "text_to_image": "m", "prompt_writer": "m", "safety_check": "m"},
    "prompts": {
        "model_prompt_writer": "s", "description_safety": "s", "image_nsfw": "s",
        "general": "s", "intimate": "s", "local_safety_check": "s",
    },
    "presets": {"preset_1": "https://cdn.example.com/preset_1.jpg"},
}


def _make_team_and_user(db, role="owner"):
    team = Team(id=new_id(), name="Test Team")
    user = User(id=new_id(), email=f"{new_id()}@example.com")
    db.add_all([team, user])
    db.commit()
    db.add(TeamMembership(id=new_id(), team_id=team.id, user_id=user.id, role=role))
    db.commit()
    return team, user


def _make_asset(db, team, user, url="http://x/files/garment.jpg"):
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


class _FakeResponse:
    content = b"fake-bytes"
    headers = {"content-type": "image/png"}

    def raise_for_status(self):
        pass


def test_resolve_model_image_generate_saves_a_new_asset(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    monkeypatch.setattr(tool, "generate_model_candidate", lambda config, *a, **k: {
        "url": "https://fal.example/candidate.png", "clean": True, "reason": "", "description": "a model",
    })
    monkeypatch.setattr(controller.httpx, "get", lambda url, timeout=60.0: _FakeResponse())
    saved = {}
    monkeypatch.setattr(controller.storage, "save", lambda key, content: saved.update(key=key, content=content))
    monkeypatch.setattr(controller.storage, "url_for", lambda key: f"http://x/files/{key}")

    payload = ModelImageResolveRequest(mode="generate", gender="Female", age_bracket="Young adult (25-30)", skin_tone="Fair", body_type="Slim")
    result = controller.resolve_model_image(db_session, team.id, user, payload)

    assert result.clean is True
    assert result.description == "a model"
    assert result.asset_id is not None
    assert saved["content"] == b"fake-bytes"
    stored = db_session.get(Asset, result.asset_id)
    assert stored.kind == AssetKind.generated.value
    assert stored.team_id == team.id


def test_resolve_model_image_generate_saves_asset_even_when_flagged(db_session, monkeypatch):
    """Same 'always show it, let a human override an obvious false
    positive' philosophy as streamlit_app.py — a flagged candidate still
    becomes a real Asset, not silently dropped."""
    team, user = _make_team_and_user(db_session)
    monkeypatch.setattr(tool, "generate_model_candidate", lambda config, *a, **k: {
        "url": "https://fal.example/candidate.png", "clean": False, "reason": "looked underage", "description": "a model",
    })
    monkeypatch.setattr(controller.httpx, "get", lambda url, timeout=60.0: _FakeResponse())
    monkeypatch.setattr(controller.storage, "save", lambda key, content: None)
    monkeypatch.setattr(controller.storage, "url_for", lambda key: f"http://x/files/{key}")

    payload = ModelImageResolveRequest(mode="generate")
    result = controller.resolve_model_image(db_session, team.id, user, payload)

    assert result.clean is False
    assert result.reason == "looked underage"
    assert result.asset_id is not None


def test_resolve_model_image_upload_requires_asset_id(db_session):
    team, user = _make_team_and_user(db_session)
    payload = ModelImageResolveRequest(mode="upload")
    with pytest.raises(HTTPException) as exc_info:
        controller.resolve_model_image(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400


def test_resolve_model_image_upload_rejects_asset_from_another_team(db_session):
    team, user = _make_team_and_user(db_session)
    other_team, other_user = _make_team_and_user(db_session)
    other_asset = _make_asset(db_session, other_team, other_user)

    payload = ModelImageResolveRequest(mode="upload", asset_id=other_asset.id)
    with pytest.raises(HTTPException) as exc_info:
        controller.resolve_model_image(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400


def test_resolve_model_image_upload_raises_when_nsfw_flagged(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    asset = _make_asset(db_session, team, user)

    def _raise(*a, **k):
        raise ValueError("flagged")

    monkeypatch.setattr(tool, "resolve_model_via_upload", _raise)

    payload = ModelImageResolveRequest(mode="upload", asset_id=asset.id)
    with pytest.raises(HTTPException) as exc_info:
        controller.resolve_model_image(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400


def test_resolve_model_image_default_uses_preset_from_config(db_session):
    team, user = _make_team_and_user(db_session)
    payload = ModelImageResolveRequest(mode="default", preset_id="preset_1")
    result = controller.resolve_model_image(db_session, team.id, user, payload)
    assert result.asset_id is None
    assert result.url == "https://cdn.example.com/preset_1.jpg"


def test_resolve_model_image_default_rejects_unknown_preset(db_session):
    team, user = _make_team_and_user(db_session)
    payload = ModelImageResolveRequest(mode="default", preset_id="nope")
    with pytest.raises(HTTPException) as exc_info:
        controller.resolve_model_image(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400


def test_build_prompts_rejects_asset_from_another_team(db_session):
    team, user = _make_team_and_user(db_session)
    other_team, other_user = _make_team_and_user(db_session)
    other_asset = _make_asset(db_session, other_team, other_user)

    payload = PromptsRequest(model_image_url="https://x/model.jpg", garment_asset_ids=[other_asset.id])
    with pytest.raises(HTTPException) as exc_info:
        controller.build_prompts(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400


def test_build_prompts_returns_prompts_and_resolved_image_size(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    garment = _make_asset(db_session, team, user, url="https://x/garment.jpg")
    monkeypatch.setattr(tool, "generate_pose_prompts_via_vlm", lambda *a, **k: ["p1", "p2"])
    monkeypatch.setattr(tool, "run_local_safety_check", lambda *a, **k: (True, ""))

    payload = PromptsRequest(
        model_image_url="https://x/model.jpg", garment_asset_ids=[garment.id],
        num_poses=2, resolution_mode="standard", aspect_ratio="3:4",
    )
    result = controller.build_prompts(db_session, team.id, user, payload)

    assert result.prompts == ["p1", "p2"]
    assert result.image_size == "portrait_4_3"
    assert result.image_urls[0] == "https://x/model.jpg"
    assert result.image_urls[1] == "https://x/garment.jpg"


def test_build_prompts_blocked_by_local_safety_check(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    garment = _make_asset(db_session, team, user, url="https://x/garment.jpg")
    monkeypatch.setattr(tool, "generate_pose_prompts_via_vlm", lambda *a, **k: ["p1"])
    monkeypatch.setattr(tool, "run_local_safety_check", lambda *a, **k: (False, "looked underage"))

    payload = PromptsRequest(model_image_url="https://x/model.jpg", garment_asset_ids=[garment.id], num_poses=1)
    with pytest.raises(HTTPException) as exc_info:
        controller.build_prompts(db_session, team.id, user, payload)
    assert exc_info.value.status_code == 400
    assert "looked underage" in exc_info.value.detail
