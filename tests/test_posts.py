from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def sample_row(**overrides: object) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 1,
        "slug": "hello-world",
        "title": "Hello",
        "description": "Intro",
        "type": "guide",
        "tags": ["python"],
        "body": "# Hello",
        "ticker": None,
        "cover": None,
        "locale": "ko",
        "draft": False,
        "published_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-02T00:00:00+00:00",
        "created_at": "2026-08-01T00:00:00+00:00",
    }
    row.update(overrides)
    return row


class FakeResponse:
    def __init__(self, data: list[dict[str, Any]], count: int | None = None) -> None:
        self.data = data
        self.count = len(data) if count is None else count


class FakeQuery:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.filters: list[tuple[str, object]] = []
        self.inserted: dict[str, Any] | None = None
        self.updated: dict[str, Any] | None = None
        self.updates: list[dict[str, Any]] = []
        self.deleted = False
        self.ordered: tuple[str, bool, bool | None] | None = None
        self.ranged: tuple[int, int] | None = None
        self.limited: int | None = None

    def select(self, *_: object, count: object = None) -> "FakeQuery":
        self.filters.append(("count", count))
        return self

    def eq(self, column: str, value: object) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def contains(self, column: str, value: object) -> "FakeQuery":
        self.filters.append((f"contains:{column}", value))
        return self

    def is_(self, column: str, value: object) -> "FakeQuery":
        self.filters.append((f"is:{column}", value))
        return self

    def order(
        self, column: str, *, desc: bool = False, nullsfirst: bool | None = None
    ) -> "FakeQuery":
        self.ordered = (column, desc, nullsfirst)
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self.ranged = (start, end)
        return self

    def limit(self, count: int) -> "FakeQuery":
        self.limited = count
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeQuery":
        self.inserted = payload
        return self

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self.updated = payload
        self.updates.append(payload)
        return self

    def delete(self) -> "FakeQuery":
        self.deleted = True
        return self

    async def execute(self) -> FakeResponse:
        return self.response


class SequencedQuery(FakeQuery):
    def __init__(self, responses: list[FakeResponse]) -> None:
        super().__init__(responses[0])
        self.responses = list(responses)

    async def execute(self) -> FakeResponse:  # type: ignore[override]
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, query: FakeQuery) -> None:
        self.query = query

    def table(self, name: str) -> FakeQuery:
        assert name == "posts"
        return self.query


class FailingQuery(FakeQuery):
    async def execute(self) -> FakeResponse:  # type: ignore[override]
        raise httpx.ConnectError("private upstream details")


class FailingClient:
    def table(self, name: str) -> FailingQuery:
        assert name == "posts"
        return FailingQuery(FakeResponse([]))


def make_app() -> tuple[object, Settings]:
    settings = Settings(
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
        SUPABASE_SECRET_KEY="sb_secret_test",
        BLOG_API_KEY="blog-test-key",
    )
    return create_app(settings), settings


def override_client(app: object, fake: FakeClient) -> None:
    from app.integrations.supabase import get_admin_client

    async def admin_client():
        yield fake

    app.dependency_overrides[get_admin_client] = admin_client  # type: ignore[attr-defined]


def test_public_list_hides_drafts_and_returns_camel_case() -> None:
    app, _ = make_app()
    query = FakeQuery(FakeResponse([sample_row()], count=1))
    override_client(app, FakeClient(query))

    response = TestClient(app).get(
        "/api/posts?type=guide&tag=python&locale=ko&limit=10"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["slug"] == "hello-world"
    assert body["items"][0]["publishedAt"] == "2026-08-01T00:00:00Z"
    assert "id" not in body["items"][0]
    assert ("draft", False) in query.filters
    assert ("type", "guide") in query.filters
    assert ("contains:tags", ["python"]) in query.filters
    assert ("locale", "ko") in query.filters
    assert query.ordered == ("published_at", True, False)
    assert query.ranged == (0, 9)


def test_include_drafts_requires_blog_key() -> None:
    app, _ = make_app()
    override_client(app, FakeClient(FakeQuery(FakeResponse([]))))

    response = TestClient(app).get("/api/posts?includeDrafts=true")

    assert response.status_code == 401
    assert response.json()["code"] == "administrator_authentication_required"


def test_include_drafts_with_key_skips_draft_filter() -> None:
    app, _ = make_app()
    query = FakeQuery(FakeResponse([sample_row(draft=True)], count=1))
    override_client(app, FakeClient(query))

    response = TestClient(app).get(
        "/api/posts?includeDrafts=true",
        headers={"X-Blog-Key": "blog-test-key"},
    )

    assert response.status_code == 200
    assert ("draft", False) not in query.filters
    assert response.json()["items"][0]["draft"] is True


def test_admin_detail_with_key_can_load_drafts() -> None:
    app, _ = make_app()
    query = FakeQuery(FakeResponse([sample_row(draft=True)]))
    override_client(app, FakeClient(query))

    response = TestClient(app).get(
        "/api/posts/hello-world?includeDrafts=true",
        headers={"X-Blog-Key": "blog-test-key"},
    )

    assert response.status_code == 200
    assert ("draft", False) not in query.filters
    assert response.json()["draft"] is True


def test_public_detail_filters_drafts() -> None:
    app, _ = make_app()
    query = FakeQuery(FakeResponse([sample_row()]))
    override_client(app, FakeClient(query))

    response = TestClient(app).get("/api/posts/hello-world")

    assert response.status_code == 200
    assert ("slug", "hello-world") in query.filters
    assert ("draft", False) in query.filters
    assert query.limited == 1


def test_missing_post_returns_404() -> None:
    app, _ = make_app()
    override_client(app, FakeClient(FakeQuery(FakeResponse([]))))

    response = TestClient(app).get("/api/posts/missing")

    assert response.status_code == 404
    assert response.json()["code"] == "post_not_found"


def test_create_post_requires_key_and_inserts_snake_case() -> None:
    app, _ = make_app()
    query = FakeQuery(FakeResponse([sample_row()]))
    override_client(app, FakeClient(query))

    response = TestClient(app).post(
        "/api/posts",
        headers={"X-Blog-Key": "blog-test-key"},
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
    assert query.inserted is not None
    assert query.inserted["slug"] == "hello-world"
    assert query.inserted["type"] == "guide"
    assert response.json()["createdAt"] == "2026-08-01T00:00:00Z"


def test_create_published_post_stamps_publish_time() -> None:
    app, _ = make_app()
    query = FakeQuery(FakeResponse([sample_row()]))
    override_client(app, FakeClient(query))

    response = TestClient(app).post(
        "/api/posts",
        headers={"X-Blog-Key": "blog-test-key"},
        json={"slug": "hello-world", "title": "Hello", "type": "guide", "body": "hi"},
    )

    assert response.status_code == 201
    assert query.inserted is not None
    stamped = datetime.fromisoformat(query.inserted["published_at"])
    assert stamped.tzinfo is not None
    assert abs((datetime.now(UTC) - stamped).total_seconds()) < 60


def test_create_draft_post_leaves_publish_time_empty() -> None:
    app, _ = make_app()
    query = FakeQuery(FakeResponse([sample_row(draft=True, published_at=None)]))
    override_client(app, FakeClient(query))

    response = TestClient(app).post(
        "/api/posts",
        headers={"X-Blog-Key": "blog-test-key"},
        json={
            "slug": "hello-world",
            "title": "Hello",
            "type": "guide",
            "body": "hi",
            "draft": True,
        },
    )

    assert response.status_code == 201
    assert query.inserted is not None
    assert "published_at" not in query.inserted
    assert response.json()["publishedAt"] is None


def test_create_post_keeps_explicit_publish_time() -> None:
    app, _ = make_app()
    query = FakeQuery(FakeResponse([sample_row()]))
    override_client(app, FakeClient(query))

    response = TestClient(app).post(
        "/api/posts",
        headers={"X-Blog-Key": "blog-test-key"},
        json={
            "slug": "hello-world",
            "title": "Hello",
            "type": "guide",
            "body": "hi",
            "publishedAt": "2026-08-01T09:30:00Z",
        },
    )

    assert response.status_code == 201
    assert query.inserted is not None
    assert datetime.fromisoformat(query.inserted["published_at"]) == datetime(
        2026, 8, 1, 9, 30, tzinfo=UTC
    )


def test_patch_post_updates_by_slug() -> None:
    app, _ = make_app()
    query = FakeQuery(FakeResponse([sample_row(title="Updated")]))
    override_client(app, FakeClient(query))

    response = TestClient(app).patch(
        "/api/posts/hello-world",
        headers={"X-Blog-Key": "blog-test-key"},
        json={"title": "Updated"},
    )

    assert response.status_code == 200
    assert query.updated == {"title": "Updated"}
    assert ("slug", "hello-world") in query.filters
    assert response.json()["title"] == "Updated"


def test_patch_publishing_stamps_missing_publish_time() -> None:
    app, _ = make_app()
    published = sample_row(draft=False, published_at="2026-08-05T02:15:00+00:00")
    query = SequencedQuery(
        [
            FakeResponse([sample_row(draft=False, published_at=None)]),
            FakeResponse([published]),
        ]
    )
    override_client(app, FakeClient(query))

    response = TestClient(app).patch(
        "/api/posts/hello-world",
        headers={"X-Blog-Key": "blog-test-key"},
        json={"draft": False},
    )

    assert response.status_code == 200
    assert len(query.updates) == 2
    assert query.updates[0] == {"draft": False}
    stamped = datetime.fromisoformat(query.updates[1]["published_at"])
    assert abs((datetime.now(UTC) - stamped).total_seconds()) < 60
    assert ("is:published_at", None) in query.filters
    assert response.json()["publishedAt"] == "2026-08-05T02:15:00Z"


def test_patch_publishing_keeps_existing_publish_time() -> None:
    app, _ = make_app()
    query = FakeQuery(FakeResponse([sample_row(draft=False)]))
    override_client(app, FakeClient(query))

    response = TestClient(app).patch(
        "/api/posts/hello-world",
        headers={"X-Blog-Key": "blog-test-key"},
        json={"draft": False},
    )

    assert response.status_code == 200
    assert query.updates == [{"draft": False}]
    assert response.json()["publishedAt"] == "2026-08-01T00:00:00Z"


def test_patch_to_draft_does_not_stamp_publish_time() -> None:
    app, _ = make_app()
    query = FakeQuery(FakeResponse([sample_row(draft=True, published_at=None)]))
    override_client(app, FakeClient(query))

    response = TestClient(app).patch(
        "/api/posts/hello-world",
        headers={"X-Blog-Key": "blog-test-key"},
        json={"draft": True},
    )

    assert response.status_code == 200
    assert query.updates == [{"draft": True}]
    assert response.json()["publishedAt"] is None


def test_patch_publish_stamp_lost_race_still_returns_post() -> None:
    app, _ = make_app()
    query = SequencedQuery(
        [
            FakeResponse([sample_row(draft=False, published_at=None)]),
            FakeResponse([]),
        ]
    )
    override_client(app, FakeClient(query))

    response = TestClient(app).patch(
        "/api/posts/hello-world",
        headers={"X-Blog-Key": "blog-test-key"},
        json={"draft": False},
    )

    assert response.status_code == 200
    assert response.json()["publishedAt"] is None


def test_empty_patch_is_rejected() -> None:
    app, _ = make_app()
    override_client(app, FakeClient(FakeQuery(FakeResponse([]))))

    response = TestClient(app).patch(
        "/api/posts/hello-world",
        headers={"X-Blog-Key": "blog-test-key"},
        json={},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_delete_post_returns_204() -> None:
    app, _ = make_app()
    query = FakeQuery(FakeResponse([sample_row()]))
    override_client(app, FakeClient(query))

    response = TestClient(app).delete(
        "/api/posts/hello-world",
        headers={"X-Blog-Key": "blog-test-key"},
    )

    assert response.status_code == 204
    assert query.deleted is True
    assert ("slug", "hello-world") in query.filters


def test_delete_missing_post_returns_404() -> None:
    app, _ = make_app()
    override_client(app, FakeClient(FakeQuery(FakeResponse([]))))

    response = TestClient(app).delete(
        "/api/posts/missing",
        headers={"X-Blog-Key": "blog-test-key"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "post_not_found"


def test_invalid_type_is_rejected() -> None:
    app, _ = make_app()
    override_client(app, FakeClient(FakeQuery(FakeResponse([]))))

    response = TestClient(app).post(
        "/api/posts",
        headers={"X-Blog-Key": "blog-test-key"},
        json={"slug": "x", "title": "x", "type": "essay", "body": "body"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_store_outage_is_sanitized() -> None:
    app, _ = make_app()
    override_client(app, FailingClient())  # type: ignore[arg-type]

    response = TestClient(app).get("/api/posts")

    assert response.status_code == 503
    assert response.json()["code"] == "database_unavailable"
    assert "private" not in response.json()["message"]
