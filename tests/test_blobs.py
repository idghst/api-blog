from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.test_posts import FakeQuery, FakeResponse

TINY_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
TINY_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
    b"\xc0P\x0f\x00\x04\x85\x01\x80\x84\xa9\x8c!\x00\x00\x00\x00IEND\xaeB`\x82"
)


def sample_blob(**overrides: object) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": "11111111-1111-4111-8111-111111111111",
        "description": "금리와 주가의 역관계",
        "mime_type": "image/png",
        "bytes": r"\x" + TINY_PNG_BYTES.hex(),
        "created_at": "2026-08-23T00:00:00+00:00",
    }
    row.update(overrides)
    return row


class BlobFakeClient:
    def __init__(self, query: FakeQuery) -> None:
        self.query = query
        self.requested: list[str] = []

    def table(self, name: str) -> FakeQuery:
        self.requested.append(name)
        assert name == "blobs"
        return self.query


def make_app() -> tuple[object, Settings]:
    settings = Settings(
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
        SUPABASE_SECRET_KEY="sb_secret_test",
        BLOG_API_KEY="blog-test-key",
    )
    return create_app(settings), settings


def override_client(app: object, fake: BlobFakeClient) -> None:
    from app.integrations.supabase import get_admin_client

    async def admin_client():
        yield fake

    app.dependency_overrides[get_admin_client] = admin_client  # type: ignore[attr-defined]


def test_create_blob_requires_blog_key() -> None:
    app, _ = make_app()
    override_client(app, BlobFakeClient(FakeQuery(FakeResponse([]))))

    response = TestClient(app).post(
        "/api/blobs",
        json={
            "description": "금리와 주가의 역관계",
            "mimeType": "image/png",
            "contentBase64": TINY_PNG,
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "administrator_authentication_required"


def test_create_blob_inserts_bytes_and_returns_meta() -> None:
    app, _ = make_app()
    query = FakeQuery(FakeResponse([sample_blob()]))
    override_client(app, BlobFakeClient(query))

    response = TestClient(app).post(
        "/api/blobs",
        headers={"X-Blog-Key": "blog-test-key"},
        json={
            "description": "금리와 주가의 역관계",
            "mimeType": "image/png",
            "contentBase64": TINY_PNG,
        },
    )

    assert response.status_code == 201
    assert query.inserted is not None
    assert query.inserted["description"] == "금리와 주가의 역관계"
    assert query.inserted["mime_type"] == "image/png"
    assert str(query.inserted["bytes"]).startswith("\\x")
    body = response.json()
    assert body["id"] == "11111111-1111-4111-8111-111111111111"
    assert body["description"] == "금리와 주가의 역관계"
    assert body["mimeType"] == "image/png"
    assert "bytes" not in body
    assert "contentBase64" not in body


def test_create_blob_rejects_non_image_mime() -> None:
    app, _ = make_app()
    override_client(app, BlobFakeClient(FakeQuery(FakeResponse([]))))

    response = TestClient(app).post(
        "/api/blobs",
        headers={"X-Blog-Key": "blog-test-key"},
        json={
            "description": "영상",
            "mimeType": "video/mp4",
            "contentBase64": TINY_PNG,
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_get_blob_returns_image_bytes() -> None:
    app, _ = make_app()
    query = FakeQuery(FakeResponse([sample_blob()]))
    override_client(app, BlobFakeClient(query))

    response = TestClient(app).get("/api/blobs/11111111-1111-4111-8111-111111111111")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content == TINY_PNG_BYTES
    assert ("id", "11111111-1111-4111-8111-111111111111") in query.filters


def test_get_blob_meta_hides_bytes() -> None:
    app, _ = make_app()
    query = FakeQuery(FakeResponse([sample_blob()]))
    override_client(app, BlobFakeClient(query))

    response = TestClient(app).get(
        "/api/blobs/11111111-1111-4111-8111-111111111111/meta"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["description"] == "금리와 주가의 역관계"
    assert "bytes" not in body


def test_missing_blob_returns_404() -> None:
    app, _ = make_app()
    override_client(app, BlobFakeClient(FakeQuery(FakeResponse([]))))

    response = TestClient(app).get("/api/blobs/11111111-1111-4111-8111-111111111111")

    assert response.status_code == 404
    assert response.json()["code"] == "blob_not_found"
