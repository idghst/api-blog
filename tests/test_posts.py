from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import BLOG_KEY, Sql, make_settings, seed_post

AUTH = {"X-Blog-Key": BLOG_KEY}


def test_public_list_hides_drafts_filters_and_returns_camel_case(
    client: TestClient, sql: Sql
) -> None:
    seed_post(sql)
    seed_post(sql, slug="draft", draft=True)
    seed_post(sql, slug="news", type="news")
    seed_post(sql, slug="other-tag", tags=["rust"])
    seed_post(sql, slug="english", locale="en")

    response = client.get("/api/posts?type=guide&tag=python&locale=ko&limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert [item["slug"] for item in body["items"]] == ["hello-world"]
    item = body["items"][0]
    assert item["publishedAt"] == "2026-08-01T00:00:00Z"
    assert item["tags"] == ["python"]
    assert item["viewCount"] == 0
    assert "id" not in item


def test_list_orders_by_publish_time_with_nulls_last_and_pages(
    client: TestClient, sql: Sql
) -> None:
    seed_post(sql, slug="old", published_at="2026-08-01T00:00:00Z")
    seed_post(sql, slug="new", published_at="2026-08-03T00:00:00Z")
    seed_post(sql, slug="unstamped", published_at=None)

    first = client.get("/api/posts?limit=2").json()
    second = client.get("/api/posts?limit=2&offset=2").json()

    assert [item["slug"] for item in first["items"]] == ["new", "old"]
    assert first["count"] == 3
    assert [item["slug"] for item in second["items"]] == ["unstamped"]
    assert second["count"] == 3


def test_offset_past_the_end_keeps_the_previous_error(
    client: TestClient, sql: Sql
) -> None:
    seed_post(sql)

    assert client.get("/api/posts?offset=1").json()["items"] == []
    response = client.get("/api/posts?offset=2")

    assert response.status_code == 502
    assert response.json()["code"] == "database_request_failed"


def test_include_drafts_requires_blog_key(client: TestClient) -> None:
    response = client.get("/api/posts?includeDrafts=true")

    assert response.status_code == 401
    assert response.json()["code"] == "administrator_authentication_required"


def test_include_drafts_with_key_returns_drafts(client: TestClient, sql: Sql) -> None:
    seed_post(sql, draft=True)

    response = client.get("/api/posts?includeDrafts=true", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["items"][0]["draft"] is True


def test_admin_detail_with_key_can_load_drafts(client: TestClient, sql: Sql) -> None:
    seed_post(sql, draft=True)

    response = client.get("/api/posts/hello-world?includeDrafts=true", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["draft"] is True


def test_public_detail_hides_drafts(client: TestClient, sql: Sql) -> None:
    seed_post(sql)
    seed_post(sql, slug="draft", draft=True)

    assert client.get("/api/posts/hello-world").status_code == 200
    response = client.get("/api/posts/draft")

    assert response.status_code == 404
    assert response.json()["code"] == "post_not_found"


def test_create_post_requires_key(client: TestClient) -> None:
    response = client.post(
        "/api/posts", json={"slug": "x", "title": "x", "type": "guide", "body": "b"}
    )

    assert response.status_code == 401


def test_create_post_stores_snake_case_and_stamps_publish_time(
    client: TestClient, sql: Sql
) -> None:
    response = client.post(
        "/api/posts",
        headers=AUTH,
        json={
            "slug": "hello-world",
            "title": "Hello",
            "description": "Intro",
            "type": "guide",
            "tags": ["python"],
            "body": "# Hello",
            "locale": "ko",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "hello-world"
    assert body["createdAt"].endswith("Z")
    stamped = datetime.fromisoformat(body["publishedAt"])
    assert abs((datetime.now(UTC) - stamped).total_seconds()) < 60
    row = sql("select tags, type from blog.posts where slug = 'hello-world'")[0]
    assert row == {"tags": ["python"], "type": "guide"}


def test_create_draft_post_leaves_publish_time_empty(client: TestClient) -> None:
    response = client.post(
        "/api/posts",
        headers=AUTH,
        json={"slug": "d", "title": "D", "type": "guide", "body": "b", "draft": True},
    )

    assert response.status_code == 201
    assert response.json()["publishedAt"] is None


def test_create_post_keeps_explicit_publish_time(client: TestClient) -> None:
    response = client.post(
        "/api/posts",
        headers=AUTH,
        json={
            "slug": "x",
            "title": "X",
            "type": "guide",
            "body": "b",
            "publishedAt": "2026-08-01T18:30:00+09:00",
        },
    )

    assert response.status_code == 201
    assert response.json()["publishedAt"] == "2026-08-01T09:30:00Z"


def test_duplicate_slug_returns_409(client: TestClient, sql: Sql) -> None:
    seed_post(sql)

    response = client.post(
        "/api/posts",
        headers=AUTH,
        json={"slug": "hello-world", "title": "X", "type": "guide", "body": "b"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "post_slug_exists"


def test_patch_post_updates_by_slug(client: TestClient, sql: Sql) -> None:
    seed_post(sql)

    response = client.patch(
        "/api/posts/hello-world",
        headers=AUTH,
        json={"title": "Updated", "tags": ["a", "b"]},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated"
    assert response.json()["tags"] == ["a", "b"]


def test_patch_publishing_stamps_missing_publish_time(
    client: TestClient, sql: Sql
) -> None:
    seed_post(sql, draft=True, published_at=None)

    response = client.patch(
        "/api/posts/hello-world", headers=AUTH, json={"draft": False}
    )

    assert response.status_code == 200
    stamped = datetime.fromisoformat(response.json()["publishedAt"])
    assert abs((datetime.now(UTC) - stamped).total_seconds()) < 60


def test_patch_publishing_keeps_existing_publish_time(
    client: TestClient, sql: Sql
) -> None:
    seed_post(sql, draft=True)

    response = client.patch(
        "/api/posts/hello-world", headers=AUTH, json={"draft": False}
    )

    assert response.json()["publishedAt"] == "2026-08-01T00:00:00Z"


def test_patch_to_draft_does_not_stamp_publish_time(
    client: TestClient, sql: Sql
) -> None:
    seed_post(sql, draft=False, published_at=None)

    response = client.patch(
        "/api/posts/hello-world", headers=AUTH, json={"draft": True}
    )

    assert response.status_code == 200
    assert response.json()["publishedAt"] is None


def test_patch_missing_post_returns_404(client: TestClient, sql: Sql) -> None:
    response = client.patch("/api/posts/missing", headers=AUTH, json={"title": "x"})

    assert response.status_code == 404
    assert response.json()["code"] == "post_not_found"


def test_empty_patch_is_rejected(client: TestClient) -> None:
    response = client.patch("/api/posts/hello-world", headers=AUTH, json={})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_delete_post_returns_204_then_404(client: TestClient, sql: Sql) -> None:
    seed_post(sql)

    assert client.delete("/api/posts/hello-world", headers=AUTH).status_code == 204
    response = client.delete("/api/posts/hello-world", headers=AUTH)

    assert response.status_code == 404
    assert response.json()["code"] == "post_not_found"


def test_invalid_type_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/posts",
        headers=AUTH,
        json={"slug": "x", "title": "x", "type": "essay", "body": "body"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_store_outage_is_sanitized() -> None:
    app = create_app(
        make_settings(DATABASE_URL="postgresql://u:secret@127.0.0.1:1/blog")
    )

    response = TestClient(app).get("/api/posts")

    assert response.status_code == 503
    assert response.json()["code"] == "database_unavailable"
    assert "secret" not in response.text
