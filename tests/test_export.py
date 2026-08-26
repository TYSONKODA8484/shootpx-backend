"""tests/test_export.py — export_asset's credit-check, preset-validation,
and asset-creation logic. Storage is monkeypatched; image_ops runs for
real (fast, in-memory, no reason to mock Pillow itself)."""

import io

import pytest
from fastapi import HTTPException
from PIL import Image

from app.controllers import asset_controller
from app.models.asset import Asset, AssetKind
from app.models.credit import CreditReason, TeamCreditBalance
from app.models.team import Team, TeamMembership, new_id
from app.models.user import User


def _make_team_and_user(db, balance=10, role="owner"):
    team = Team(id=new_id(), name="Test Team")
    user = User(id=new_id(), email=f"{new_id()}@example.com")
    db.add_all([team, user])
    db.commit()
    db.add(TeamMembership(id=new_id(), team_id=team.id, user_id=user.id, role=role))
    db.add(TeamCreditBalance(team_id=team.id, balance=balance))
    db.commit()
    return team, user


def _make_source_asset(db, team, user):
    buf = io.BytesIO()
    Image.new("RGB", (800, 400), (200, 30, 30)).save(buf, format="PNG")
    asset = Asset(
        team_id=team.id, created_by=user.id, kind=AssetKind.upload.value, media_type="image",
        storage_key=f"{team.id}/source.png", url=f"http://x/files/{team.id}/source.png",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset, buf.getvalue()


def test_export_asset_creates_one_asset_per_preset_and_deducts_credits(db_session, monkeypatch):
    # apply_credit_delta (core/credits.py) runs Postgres-only raw SQL
    # (ON CONFLICT, now()) that the sqlite test fixture can't execute — same
    # boundary already mocked at storage/cache seams elsewhere in this
    # suite. Monkeypatched here rather than exercised for real; the credits
    # ledger itself is proven against the real DB, not by this unit test.
    calls = []
    monkeypatch.setattr(
        asset_controller, "apply_credit_delta",
        lambda db, team_id, amount, reason, reference_id=None: calls.append((team_id, amount, reason, reference_id)),
    )
    team, user = _make_team_and_user(db_session, balance=10)
    source, source_bytes = _make_source_asset(db_session, team, user)
    monkeypatch.setattr(asset_controller.storage, "read", lambda key: source_bytes)
    saved = []
    monkeypatch.setattr(asset_controller.storage, "save", lambda key, content: saved.append(key))

    result = asset_controller.export_asset(db_session, source.id, user, ["shopify_product", "master_png"])

    assert len(result.exports) == 2
    assert len(saved) == 2
    exported_rows = db_session.query(Asset).filter(Asset.kind == AssetKind.exported.value).all()
    assert len(exported_rows) == 2
    assert all(r.source_asset_id == source.id for r in exported_rows)

    assert calls == [(team.id, -2, CreditReason.export_spend.value, source.id)]


def test_export_asset_402s_when_insufficient_credits(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session, balance=1)
    source, source_bytes = _make_source_asset(db_session, team, user)
    monkeypatch.setattr(asset_controller.storage, "read", lambda key: source_bytes)
    monkeypatch.setattr(asset_controller.storage, "save", lambda key, content: None)

    with pytest.raises(HTTPException) as exc_info:
        asset_controller.export_asset(db_session, source.id, user, ["shopify_product", "master_png"])
    assert exc_info.value.status_code == 402


def test_export_asset_400s_for_an_unknown_preset(db_session):
    team, user = _make_team_and_user(db_session)
    source, _bytes = _make_source_asset(db_session, team, user)

    with pytest.raises(HTTPException) as exc_info:
        asset_controller.export_asset(db_session, source.id, user, ["not_a_real_preset"])
    assert exc_info.value.status_code == 400


def test_export_asset_404s_for_a_missing_source_asset(db_session):
    _team, user = _make_team_and_user(db_session)

    with pytest.raises(HTTPException) as exc_info:
        asset_controller.export_asset(db_session, "does-not-exist", user, ["shopify_product"])
    assert exc_info.value.status_code == 404


def test_export_asset_404s_for_a_non_member(db_session):
    team, owner = _make_team_and_user(db_session)
    _, outsider = _make_team_and_user(db_session)
    source, _bytes = _make_source_asset(db_session, team, owner)

    with pytest.raises(HTTPException) as exc_info:
        asset_controller.export_asset(db_session, source.id, outsider, ["shopify_product"])
    assert exc_info.value.status_code == 404
