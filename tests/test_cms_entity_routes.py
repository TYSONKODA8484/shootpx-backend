def _login(client):
    client.post("/cms/login", json={"password": "test-password"})


def test_entities_route_requires_auth(client):
    response = client.get("/cms/entities/plans")
    assert response.status_code == 401


def test_plans_crud_over_http(client):
    _login(client)

    create_response = client.post("/cms/entities/plans", json={
        "name": "Starter", "billing_cycle": "monthly", "price": 99900,
        "currency": "INR", "credit_allowance": 100, "max_team_members": 5,
        "is_active": True,
    })
    assert create_response.status_code == 200
    plan_id = create_response.json()["id"]

    list_response = client.get("/cms/entities/plans")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    update_response = client.patch(f"/cms/entities/plans/{plan_id}", json={"credit_allowance": 200})
    assert update_response.status_code == 200

    delete_response = client.delete(f"/cms/entities/plans/{plan_id}")
    assert delete_response.status_code == 200


def test_entities_schema_route(client):
    _login(client)
    response = client.get("/cms/entities")
    assert response.status_code == 200
    names = {e["name"] for e in response.json()}
    assert len(names) == 19
    assert "plans" in names


def test_stats_route(client):
    _login(client)
    response = client.get("/cms/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["total_users"] == 0
    assert body["total_teams"] == 0
