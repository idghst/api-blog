import os
from collections.abc import Callable, Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from pydantic_settings import SettingsConfigDict

from app.core.config import Settings, clear_settings_cache

# 연결하지 않는 단위 테스트용 기본값. DB 테스트는 아래 TEST_* URL을 쓴다.
os.environ.setdefault("DATABASE_URL", "postgresql://blog_app@127.0.0.1:1/blog")
Settings.model_config = SettingsConfigDict(env_file=None, extra="ignore")

from app.main import create_app

# 스키마를 비우고 채우는 관리자 접속(소유자/슈퍼유저)과 앱이 쓰는 접속(blog_app 권장).
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
TEST_APP_DATABASE_URL = os.environ.get("TEST_APP_DATABASE_URL", TEST_DATABASE_URL)
BLOG_KEY = "blog-test-key"

type Sql = Callable[..., list[dict[str, Any]]]


@pytest.fixture(autouse=True)
def clear_cached_settings() -> Iterator[None]:
    clear_settings_cache()
    yield
    clear_settings_cache()


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "DATABASE_URL": TEST_APP_DATABASE_URL or os.environ["DATABASE_URL"],
        "BLOG_API_KEY": BLOG_KEY,
        "VIEW_HASH_SALT": "view-salt",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def sql() -> Iterator[Sql]:
    """관리자 접속으로 SQL을 실행한다. 테스트마다 blog 테이블을 비운다."""

    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL이 없어 DB 테스트를 건너뛴다")
    with psycopg.connect(
        TEST_DATABASE_URL, autocommit=True, row_factory=dict_row
    ) as conn:
        conn.execute("truncate blog.posts, blog.blobs cascade")

        def run(query: Any, params: Any = None) -> list[dict[str, Any]]:
            cursor = conn.execute(query, params)
            return cursor.fetchall() if cursor.description else []

        yield run


@pytest.fixture
def client(sql: Sql) -> TestClient:
    return TestClient(create_app(make_settings()))


def seed_post(sql: Sql, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "slug": "hello-world",
        "title": "Hello",
        "description": "Intro",
        "type": "guide",
        "tags": ["python"],
        "body": "# Hello",
        "locale": "ko",
        "draft": False,
        "published_at": "2026-08-01T00:00:00+00:00",
    }
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(["%s"] * len(values))
    return sql(
        f"insert into blog.posts ({columns}) values ({placeholders}) returning *",
        list(values.values()),
    )[0]
