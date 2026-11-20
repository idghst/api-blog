import pytest
from fastapi.testclient import TestClient

from app.core.errors import ApiError
from app.integrations.postgres import require_blog_api_key
from app.main import create_app
from tests.conftest import make_settings


def test_write_routes_require_blog_key() -> None:
    client = TestClient(create_app(make_settings()))

    response = client.post(
        "/api/posts",
        json={"slug": "hello", "title": "Hello", "type": "guide", "body": "body"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "administrator_authentication_required"


def test_wrong_blog_key_is_rejected() -> None:
    with pytest.raises(ApiError) as raised:
        require_blog_api_key(make_settings(), "wrong")

    assert raised.value.status_code == 401


def test_missing_blog_api_key_config_returns_503() -> None:
    with pytest.raises(ApiError) as raised:
        require_blog_api_key(make_settings(BLOG_API_KEY=None), "anything")

    assert raised.value.status_code == 503
    assert raised.value.code == "administrator_authentication_unavailable"
