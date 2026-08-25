def test_me_requires_auth(client):
    response = client.get("/cms/me")
    assert response.status_code == 401


def test_login_wrong_password_rejected(client):
    response = client.post("/cms/login", json={"password": "wrong"})
    assert response.status_code == 401


def test_login_then_me_succeeds(client):
    login_response = client.post("/cms/login", json={"password": "test-password"})
    assert login_response.status_code == 200
    assert "cms_session" in login_response.cookies

    me_response = client.get("/cms/me")
    assert me_response.status_code == 200
    assert me_response.json() == {"authenticated": True}


def test_logout_clears_session(client):
    client.post("/cms/login", json={"password": "test-password"})
    client.post("/cms/logout")
    response = client.get("/cms/me")
    assert response.status_code == 401
