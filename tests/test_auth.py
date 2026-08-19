from typing import cast

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import ApiError
from app.main import create_app
from supabase import AsyncClient, AsyncClientOptions


class FakeHttpClient:
    def __init__(self, **_: object) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.postgrest = object()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
    )


@pytest.mark.asyncio
async def test_admin_client_uses_only_secret_key_and_closes_client(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    from app.integrations import supabase
    from app.integrations.supabase import get_admin_client

    http_client = FakeHttpClient()
    supabase_client = FakeSupabaseClient()
    received_keys: list[str] = []
    options: list[AsyncClientOptions] = []
    monkeypatch.setattr(supabase.httpx, "AsyncClient", lambda **_: http_client)

    async def create_client(*args: object, **kwargs: object) -> FakeSupabaseClient:
        received_keys.append(cast(str, args[1]))
        options.append(cast(AsyncClientOptions, kwargs["options"]))
        return supabase_client

    monkeypatch.setattr(supabase, "acreate_client", create_client)
    admin_settings = Settings(
        SUPABASE_URL=str(settings.SUPABASE_URL),
        SUPABASE_PUBLISHABLE_KEY=settings.SUPABASE_PUBLISHABLE_KEY,
        SUPABASE_SECRET_KEY="sb_secret_test",
    )

    clients: list[AsyncClient] = []
    async for configured_client in get_admin_client(admin_settings):
        clients.append(configured_client)

    assert clients[0] is supabase_client
    assert received_keys == ["sb_secret_test"]
    assert http_client.closed is True
    assert options[0].schema == "blog"
    assert options[0].persist_session is False
    assert options[0].auto_refresh_token is False
    assert options[0].postgrest_client_timeout == 5.0
    assert options[0].httpx_client is http_client


@pytest.mark.asyncio
async def test_admin_client_requires_secret_key(settings: Settings) -> None:
    from app.integrations.supabase import get_admin_client

    with pytest.raises(ApiError) as raised:
        async for _ in get_admin_client(settings):
            pass

    assert raised.value.status_code == 503
    assert raised.value.code == "administrator_client_unavailable"


@pytest.mark.asyncio
async def test_client_creation_failure_closes_http_client(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    from app.integrations import supabase

    http_client = FakeHttpClient()
    monkeypatch.setattr(supabase.httpx, "AsyncClient", lambda **_: http_client)

    async def create_client(*_: object, **__: object) -> FakeSupabaseClient:
        raise RuntimeError("client creation failed")

    monkeypatch.setattr(supabase, "acreate_client", create_client)

    with pytest.raises(RuntimeError, match="client creation failed"):
        await supabase._new_client(settings, "sb_publishable_test")

    assert http_client.closed is True


def test_write_routes_require_blog_key() -> None:
    app = create_app(
        Settings(
            SUPABASE_URL="https://test.supabase.co",
            SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
            SUPABASE_SECRET_KEY="sb_secret_test",
            BLOG_API_KEY="blog-test-key",
        )
    )
    client = TestClient(app)

    response = client.post(
        "/api/posts",
        json={
            "slug": "hello",
            "title": "Hello",
            "type": "guide",
            "body": "body",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "administrator_authentication_required"


def test_missing_blog_api_key_config_returns_503() -> None:
    from app.integrations.supabase import require_blog_api_key

    settings = Settings(
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
        SUPABASE_SECRET_KEY="sb_secret_test",
    )

    with pytest.raises(ApiError) as raised:
        require_blog_api_key(settings, "anything")

    assert raised.value.status_code == 503
    assert raised.value.code == "administrator_authentication_unavailable"
