from base64 import b64decode

from fastapi.testclient import TestClient

from tests.conftest import BLOG_KEY, Sql

TINY_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
TINY_PNG_BYTES = b64decode(TINY_PNG)
NEW_BLOB = {
    "description": "금리와 주가의 역관계",
    "mimeType": "image/png",
    "contentBase64": TINY_PNG,
}


def test_create_blob_requires_blog_key(client: TestClient) -> None:
    response = client.post("/api/blobs", json=NEW_BLOB)

    assert response.status_code == 401
    assert response.json()["code"] == "administrator_authentication_required"


def test_blob_round_trip_returns_meta_bytes_and_hides_content(
    client: TestClient, sql: Sql
) -> None:
    created = client.post("/api/blobs", headers={"X-Blog-Key": BLOG_KEY}, json=NEW_BLOB)

    assert created.status_code == 201
    body = created.json()
    assert set(body) == {"id", "description", "mimeType", "createdAt"}
    assert body["description"] == "금리와 주가의 역관계"
    assert body["mimeType"] == "image/png"
    stored = sql("select bytes from blog.blobs where id = %s", (body["id"],))[0]
    assert stored["bytes"] == TINY_PNG_BYTES

    image = client.get(f"/api/blobs/{body['id']}")
    meta = client.get(f"/api/blobs/{body['id']}/meta")

    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/png")
    assert image.content == TINY_PNG_BYTES
    assert meta.json() == body


def test_create_blob_rejects_non_image_mime(client: TestClient) -> None:
    response = client.post(
        "/api/blobs",
        headers={"X-Blog-Key": BLOG_KEY},
        json={**NEW_BLOB, "mimeType": "video/mp4"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_create_blob_rejects_invalid_base64(client: TestClient) -> None:
    response = client.post(
        "/api/blobs",
        headers={"X-Blog-Key": BLOG_KEY},
        json={**NEW_BLOB, "contentBase64": "not base64!"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_missing_blob_returns_404(client: TestClient) -> None:
    response = client.get("/api/blobs/11111111-1111-4111-8111-111111111111")

    assert response.status_code == 404
    assert response.json()["code"] == "blob_not_found"


def test_malformed_blob_id_returns_422(client: TestClient) -> None:
    response = client.get("/api/blobs/not-a-uuid/meta")

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_row"
