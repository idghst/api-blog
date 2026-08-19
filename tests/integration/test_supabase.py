import os
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.integration

_CREDENTIALS_SKIP_MESSAGE = "Supabase integration credentials are not set"
_CREDENTIAL_ENV_NAMES = (
    "SUPABASE_TEST_URL",
    "SUPABASE_TEST_PUBLISHABLE_KEY",
    "SUPABASE_TEST_SECRET_KEY",
    "SUPABASE_TEST_BLOG_API_KEY",
)


@dataclass(frozen=True)
class IntegrationCredentials:
    url: str
    publishable_key: str
    secret_key: str
    blog_api_key: str


def load_integration_credentials() -> IntegrationCredentials:
    values = {name: os.getenv(name, "").strip() for name in _CREDENTIAL_ENV_NAMES}
    if not all(values.values()):
        pytest.skip(_CREDENTIALS_SKIP_MESSAGE)
    return IntegrationCredentials(
        url=values["SUPABASE_TEST_URL"].rstrip("/"),
        publishable_key=values["SUPABASE_TEST_PUBLISHABLE_KEY"],
        secret_key=values["SUPABASE_TEST_SECRET_KEY"],
        blog_api_key=values["SUPABASE_TEST_BLOG_API_KEY"],
    )


@pytest.fixture(scope="session")
def credentials() -> IntegrationCredentials:
    return load_integration_credentials()


def test_initial_migration_creates_only_blog_schema_contract() -> None:
    migration = next(
        (Path(__file__).parents[2] / "supabase" / "migrations").glob("*_init_blog.sql")
    )

    assert (
        migration.read_text()
        == """create schema if not exists blog;

grant usage on schema blog to anon, authenticated, service_role;

alter default privileges in schema blog
  grant all on tables to service_role;

alter default privileges in schema blog
  grant all on sequences to service_role;

alter default privileges in schema blog
  grant execute on routines to service_role;
"""
    )


def test_local_data_api_exposes_blog_schema() -> None:
    config = Path(__file__).parents[2] / "supabase" / "config.toml"

    assert 'schemas = ["public", "graphql_public", "blog"]' in config.read_text()


def test_public_list_against_live_store(credentials: IntegrationCredentials) -> None:
    app = create_app(
        Settings(
            SUPABASE_URL=credentials.url,
            SUPABASE_PUBLISHABLE_KEY=credentials.publishable_key,
            SUPABASE_SECRET_KEY=credentials.secret_key,
            BLOG_API_KEY=credentials.blog_api_key,
        )
    )
    response = TestClient(app).get("/api/posts")

    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "count" in payload
