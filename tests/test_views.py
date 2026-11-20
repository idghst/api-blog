from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.visitor import resolve_visitor
from app.main import create_app
from app.services import posts
from app.services.views import KST
from tests.conftest import Sql, make_settings, seed_post

VIEW = "/api/posts/hello-world/view"


def build_request(headers: list[tuple[bytes, bytes]], client: Any = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": VIEW,
            "headers": headers,
            "client": client,
        }
    )


def test_first_view_is_counted_and_a_refresh_is_not(
    client: TestClient, sql: Sql
) -> None:
    seed_post(sql)

    first = client.post(VIEW, json={"visitorId": "device-a"})
    again = client.post(VIEW, json={"visitorId": "device-a"})
    other = client.post(VIEW, json={"visitorId": "device-b"})

    assert first.json() == {"slug": "hello-world", "viewCount": 1, "counted": True}
    assert again.json() == {"slug": "hello-world", "viewCount": 1, "counted": False}
    assert other.json() == {"slug": "hello-world", "viewCount": 2, "counted": True}


def test_view_is_bucketed_by_the_korean_calendar_day(
    client: TestClient, sql: Sql
) -> None:
    seed_post(sql)

    client.post(VIEW, json={"visitorId": "device-a"})

    rows = sql("select viewed_on from blog.post_views")
    assert rows == [{"viewed_on": datetime.now(KST).date()}]
    assert KST == timezone(timedelta(hours=9))


def test_view_without_a_visitor_id_falls_back_to_the_request_origin(
    client: TestClient, sql: Sql
) -> None:
    seed_post(sql)

    response = client.post(
        VIEW,
        headers={"X-Forwarded-For": "203.0.113.9, 70.41.3.18", "User-Agent": "probe"},
    )

    assert response.json()["counted"] is True
    visitor = sql("select visitor from blog.post_views")[0]["visitor"]
    assert len(visitor) == 64
    assert "203.0.113.9" not in visitor
    assert "probe" not in visitor


def test_unidentifiable_request_is_not_recorded(sql: Sql) -> None:
    seed_post(sql)
    client = TestClient(create_app(make_settings(VIEW_HASH_SALT=None)))

    response = client.post(VIEW, json={"visitorId": "device-a"})

    assert response.json() == {"slug": "hello-world", "viewCount": 0, "counted": False}
    assert sql("select * from blog.post_views") == []


def test_view_on_a_draft_post_is_not_found(client: TestClient, sql: Sql) -> None:
    seed_post(sql, draft=True)

    response = client.post(VIEW)

    assert response.status_code == 404
    assert response.json()["code"] == "post_not_found"


def test_blank_visitor_id_is_rejected(client: TestClient, sql: Sql) -> None:
    seed_post(sql)

    response = client.post(VIEW, json={"visitorId": ""})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_posts_list_and_detail_carry_the_view_count(
    client: TestClient, sql: Sql
) -> None:
    post = seed_post(sql)
    seed_post(sql, slug="unseen")
    sql(
        "insert into blog.post_view_counts (post_id, total) values (%s, 42)",
        (post["id"],),
    )

    items = client.get("/api/posts").json()["items"]

    assert {item["slug"]: item["viewCount"] for item in items} == {
        "hello-world": 42,
        "unseen": 0,
    }
    assert client.get("/api/posts/hello-world").json()["viewCount"] == 42
    assert client.get("/api/posts/unseen").json()["viewCount"] == 0


def test_empty_list_page_returns_no_items(client: TestClient, sql: Sql) -> None:
    response = client.get("/api/posts")

    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}


def test_corrupt_row_is_reported_as_a_store_error() -> None:
    with pytest.raises(ApiError) as raised:
        posts._output({"slug": "x", "type": "essay"})
    with pytest.raises(ApiError):
        posts._as_nonneg_int(-1)

    assert raised.value.status_code == 502
    assert raised.value.code == "database_response_invalid"


def _settings(**overrides: object) -> Settings:
    return make_settings(**overrides)


def test_visitor_id_hash_is_stable_and_unique_per_device() -> None:
    settings = _settings()
    request = build_request([])

    first = resolve_visitor(settings, request, "device-a")
    again = resolve_visitor(settings, request, "device-a")
    other = resolve_visitor(settings, request, "device-b")

    assert first == again
    assert first != other
    assert first is not None and "device-a" not in first


def test_salt_changes_the_visitor_hash() -> None:
    request = build_request([])

    first = resolve_visitor(_settings(), request, "device-a")
    second = resolve_visitor(_settings(VIEW_HASH_SALT="other"), request, "device-a")

    assert first != second


def test_request_without_any_identity_is_not_identified() -> None:
    assert resolve_visitor(_settings(), build_request([]), None) is None


def test_visitor_is_not_identified_without_a_hashing_secret() -> None:
    settings = _settings(VIEW_HASH_SALT="  ")
    request = build_request([(b"x-forwarded-for", b"203.0.113.9")])

    assert resolve_visitor(settings, request, "device-a") is None


def test_direct_client_address_is_used_when_no_proxy_header_is_present() -> None:
    settings = _settings()

    forwarded = resolve_visitor(
        settings, build_request([(b"x-forwarded-for", b"203.0.113.9")]), None
    )
    direct = resolve_visitor(settings, build_request([], ("203.0.113.9", 443)), None)

    assert forwarded is not None
    assert forwarded == direct
