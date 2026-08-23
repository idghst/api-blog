from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.test_posts import FakeQuery, FakeResponse, sample_row


def sample_comment(**overrides: object) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 1,
        "post_id": 1,
        "author": "reader",
        "body": "도움이 됐습니다.",
        "created_at": "2026-08-23T00:00:00+00:00",
    }
    row.update(overrides)
    return row


class RoutingFakeClient:
    def __init__(self, tables: dict[str, FakeQuery]) -> None:
        self.tables = tables
        self.requested: list[str] = []

    def table(self, name: str) -> FakeQuery:
        self.requested.append(name)
        assert name in self.tables
        return self.tables[name]


def make_app() -> tuple[object, Settings]:
    settings = Settings(
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
        SUPABASE_SECRET_KEY="sb_secret_test",
        BLOG_API_KEY="blog-test-key",
    )
    return create_app(settings), settings


def override_client(app: object, fake: RoutingFakeClient) -> None:
    from app.integrations.supabase import get_admin_client

    async def admin_client():
        yield fake

    app.dependency_overrides[get_admin_client] = admin_client  # type: ignore[attr-defined]


def test_list_comments_is_public_and_returns_camel_case() -> None:
    app, _ = make_app()
    posts = FakeQuery(FakeResponse([sample_row()]))
    comments = FakeQuery(FakeResponse([sample_comment()], count=1))
    fake = RoutingFakeClient({"posts": posts, "comments": comments})
    override_client(app, fake)

    response = TestClient(app).get("/api/posts/hello-world/comments")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["author"] == "reader"
    assert body["items"][0]["body"] == "도움이 됐습니다."
    assert body["items"][0]["createdAt"] == "2026-08-23T00:00:00Z"
    assert "id" in body["items"][0]
    assert ("slug", "hello-world") in posts.filters
    assert ("post_id", 1) in comments.filters
    assert comments.ordered == ("created_at", False)


def test_list_comments_for_missing_post_returns_404() -> None:
    app, _ = make_app()
    fake = RoutingFakeClient(
        {
            "posts": FakeQuery(FakeResponse([])),
            "comments": FakeQuery(FakeResponse([])),
        }
    )
    override_client(app, fake)

    response = TestClient(app).get("/api/posts/missing/comments")

    assert response.status_code == 404
    assert response.json()["code"] == "post_not_found"


def test_create_comment_is_public_and_inserts_row() -> None:
    app, _ = make_app()
    posts = FakeQuery(FakeResponse([sample_row()]))
    comments = FakeQuery(FakeResponse([sample_comment()]))
    fake = RoutingFakeClient({"posts": posts, "comments": comments})
    override_client(app, fake)

    response = TestClient(app).post(
        "/api/posts/hello-world/comments",
        json={"author": "reader", "body": "도움이 됐습니다."},
    )

    assert response.status_code == 201
    assert comments.inserted == {
        "post_id": 1,
        "author": "reader",
        "body": "도움이 됐습니다.",
    }
    assert response.json()["author"] == "reader"
    assert "X-Blog-Key" not in response.request.headers


def test_create_comment_rejects_blank_body() -> None:
    app, _ = make_app()
    override_client(
        app,
        RoutingFakeClient(
            {
                "posts": FakeQuery(FakeResponse([sample_row()])),
                "comments": FakeQuery(FakeResponse([])),
            }
        ),
    )

    response = TestClient(app).post(
        "/api/posts/hello-world/comments",
        json={"author": "reader", "body": "   "},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_create_comment_for_missing_post_returns_404() -> None:
    app, _ = make_app()
    comments = FakeQuery(FakeResponse([]))
    override_client(
        app,
        RoutingFakeClient(
            {
                "posts": FakeQuery(FakeResponse([])),
                "comments": comments,
            }
        ),
    )

    response = TestClient(app).post(
        "/api/posts/missing/comments",
        json={"author": "reader", "body": "hello"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "post_not_found"
    assert comments.inserted is None
