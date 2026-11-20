from fastapi.testclient import TestClient

from tests.conftest import Sql, seed_post


def test_list_comments_is_public_ordered_and_camel_case(
    client: TestClient, sql: Sql
) -> None:
    post = seed_post(sql)
    sql(
        "insert into blog.comments (post_id, author, body, created_at) values"
        " (%s, 'late', 'second', '2026-08-24T00:00:00Z'),"
        " (%s, 'reader', '도움이 됐습니다.', '2026-08-23T00:00:00Z')",
        (post["id"], post["id"]),
    )

    response = client.get("/api/posts/hello-world/comments")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert [item["author"] for item in body["items"]] == ["reader", "late"]
    assert body["items"][0]["body"] == "도움이 됐습니다."
    assert body["items"][0]["createdAt"] == "2026-08-23T00:00:00Z"
    assert isinstance(body["items"][0]["id"], int)


def test_list_comments_for_missing_or_draft_post_returns_404(
    client: TestClient, sql: Sql
) -> None:
    seed_post(sql, draft=True)

    for slug in ("missing", "hello-world"):
        response = client.get(f"/api/posts/{slug}/comments")
        assert response.status_code == 404
        assert response.json()["code"] == "post_not_found"


def test_create_comment_is_public_and_inserts_row(client: TestClient, sql: Sql) -> None:
    post = seed_post(sql)

    response = client.post(
        "/api/posts/hello-world/comments",
        json={"author": " reader ", "body": "도움이 됐습니다."},
    )

    assert response.status_code == 201
    assert response.json()["author"] == "reader"
    rows = sql("select post_id, author, body from blog.comments")
    assert rows == [
        {"post_id": post["id"], "author": "reader", "body": "도움이 됐습니다."}
    ]


def test_create_comment_rejects_blank_body(client: TestClient, sql: Sql) -> None:
    seed_post(sql)

    response = client.post(
        "/api/posts/hello-world/comments", json={"author": "reader", "body": "   "}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_create_comment_for_missing_post_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/posts/missing/comments", json={"author": "reader", "body": "hi"}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "post_not_found"
