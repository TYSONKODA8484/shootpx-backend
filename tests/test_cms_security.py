from app.core.security import create_cms_token, create_session_token, read_cms_token


def test_create_and_read_cms_token_roundtrip():
    token = create_cms_token()
    assert read_cms_token(token) is True


def test_read_cms_token_rejects_garbage():
    assert read_cms_token("not-a-real-token") is False


def test_read_cms_token_rejects_a_user_session_token():
    # signed with a different salt than the CMS token, even though both use
    # the same SECRET_KEY — one must never be accepted as the other
    user_token = create_session_token("some-user-id")
    assert read_cms_token(user_token) is False
