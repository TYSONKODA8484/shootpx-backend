"""GET /billing/catalog — combined pricing-page catalog: which tabs are
offered (billing_mode) plus every plan and credit pack available to buy
(Plan/CreditPack), one round trip instead of three. Public, no auth."""

from app.controllers import billing_controller
from app.models.billing_mode import BillingMode
from app.models.credit import CreditPack
from app.models.plan import Plan


def _make_free_plan(db):
    plan = Plan(
        name="Free", billing_cycle="free", price=None, credit_allowance=100,
        max_team_members=3, is_active=True,
    )
    db.add(plan)
    db.commit()
    return plan


def _make_paid_plan(db, region=None, name="Pro", price=99900):
    plan = Plan(
        name=name, billing_cycle="monthly", price=price, region=region,
        credit_allowance=5000, max_team_members=10, provider="razorpay",
        provider_plan_id=f"plan_{name.lower()}_{region or 'all'}", is_active=True,
    )
    db.add(plan)
    db.commit()
    return plan


def _make_pack(db, region=None, credit_amount=1000, price=19900):
    pack = CreditPack(name="Top-up", credit_amount=credit_amount, price=price, region=region, is_active=True)
    db.add(pack)
    db.commit()
    return pack


def test_get_billing_catalog_bundles_config_plans_and_packs(db_session):
    _make_free_plan(db_session)
    _make_paid_plan(db_session)
    _make_pack(db_session)

    result = billing_controller.get_billing_catalog(db_session)

    assert result["subscriptions_enabled"] is True
    assert result["credits_enabled"] is True
    assert len(result["plans"]) == 2
    assert len(result["credit_packs"]) == 1


def test_get_billing_catalog_respects_billing_mode_flags(db_session):
    db_session.add(BillingMode(key="credits", label="Credits", is_active=False))
    db_session.commit()
    _make_free_plan(db_session)

    result = billing_controller.get_billing_catalog(db_session)
    assert result["subscriptions_enabled"] is True
    assert result["credits_enabled"] is False


def test_get_billing_catalog_filters_plans_and_packs_by_region(db_session):
    _make_free_plan(db_session)
    _make_paid_plan(db_session, region="IN", name="Pro")
    _make_paid_plan(db_session, region="US", name="Pro")
    _make_pack(db_session, region="IN")
    _make_pack(db_session, region="US")

    result = billing_controller.get_billing_catalog(db_session, region="IN")

    plan_regions = {p.region for p in result["plans"]}
    assert plan_regions == {None, "IN"}  # Free (region-less) + only IN paid plan
    pack_regions = {p.region for p in result["credit_packs"]}
    assert pack_regions == {"IN"}


def test_billing_catalog_route_returns_bundled_response(client, db_session):
    _make_free_plan(db_session)
    _make_paid_plan(db_session)
    _make_pack(db_session)

    resp = client.get("/billing/catalog")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"subscriptions_enabled", "credits_enabled", "plans", "credit_packs"}
    assert len(body["plans"]) == 2
    assert len(body["credit_packs"]) == 1
    assert body["plans"][0]["plan_id"]  # computed field still present


def test_billing_catalog_route_requires_no_auth(client, db_session):
    resp = client.get("/billing/catalog")
    assert resp.status_code == 200
