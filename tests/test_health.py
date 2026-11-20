import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app
from tests.conftest import Sql, make_settings


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_health_and_liveness_return_ok(client: TestClient) -> None:
    for path in ("/health", "/health/live"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_readiness_checks_the_database(sql: Sql, client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_maps_unavailable_database_to_sanitized_503() -> None:
    app = create_app(
        make_settings(DATABASE_URL="postgresql://u:secret@127.0.0.1:1/blog")
    )

    response = TestClient(app).get(
        "/health/ready", headers={"X-Request-ID": "req-ready"}
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": "dependency_unavailable",
        "message": "Database is unavailable",
        "request_id": "req-ready",
    }


def test_factory_injects_supplied_settings_and_root_message(
    app: FastAPI, client: TestClient, settings: Settings
) -> None:
    assert app.state.settings is settings
    assert app.dependency_overrides[get_settings]() is settings

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Blog API"}


def test_production_host_exposes_docs_and_openapi(settings: Settings) -> None:
    client = TestClient(create_app(settings), base_url="http://api.example.com")

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 200


def test_localhost_and_test_hosts_expose_docs(settings: Settings) -> None:
    app = create_app(settings)
    for base_url in ("http://localhost:8000", "http://testserver"):
        client = TestClient(app, base_url=base_url)
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/docs").status_code == 200


def test_cors_allows_only_configured_origin(settings: Settings) -> None:
    client = TestClient(create_app(settings))

    allowed = client.options(
        "/health/live",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    denied = client.options(
        "/health/live",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    blog = client.options(
        "/health/live",
        headers={
            "Origin": "https://blog.idghst.co.kr",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert blog.headers["access-control-allow-origin"] == "https://blog.idghst.co.kr"
    assert denied.status_code == 400


def test_cors_allows_the_blog_key_header(settings: Settings) -> None:
    client = TestClient(create_app(settings))

    response = client.options(
        "/api/posts",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Blog-Key",
        },
    )

    assert response.status_code == 200
    assert "x-blog-key" in response.headers["access-control-allow-headers"].lower()
