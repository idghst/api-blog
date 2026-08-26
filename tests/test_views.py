from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.visitor import resolve_visitor
from app.services.views import KST
from tests.test_comments import RoutingFakeClient, make_app, override_client
from tests.test_posts import FakeQuery, FakeResponse, sample_row


def counts_row(total: int, post_id: int = 1) -> dict[str, Any]:
    return {"post_id": post_id, "total": total}


def build_request(headers: list[tuple[bytes, bytes]], client: Any = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/posts/hello-world/view",
            "headers": headers,
            "client": client,
        }
    )


def test_first_view_is_recorded_and_returns_the_total() -> None:
    app, _ = make_app()
    views = FakeQuery(FakeResponse([{"post_id": 1, "visitor": "hashed"}]))
    counts = FakeQuery(FakeResponse([counts_row(1)]))
    fake = RoutingFakeClient(
        {
            "posts": FakeQuery(FakeResponse([{"id": 1}])),
            "post_views": views,
            "post_view_counts": counts,
        }
    )
    override_client(app, fake)

    response = TestClient(app).post(
        "/api/posts/hello-world/view", json={"visitorId": "device-a"}
    )

    assert response.status_code == 200
    assert response.json() == {"slug": "hello-world", "viewCount": 1, "counted": True}
    assert views.upserted is not None
    assert views.upserted["post_id"] == 1
    assert views.upsert_options == {
        "ignore_duplicates": True,
        "on_conflict": "post_id,visitor,viewed_on",
    }


def test_refresh_by_the_same_visitor_is_not_counted_again() -> None:
    app, _ = make_app()
    views = FakeQuery(FakeResponse([]))
    counts = FakeQuery(FakeResponse([counts_row(7)]))
    fake = RoutingFakeClient(
        {
            "posts": FakeQuery(FakeResponse([{"id": 1}])),
            "post_views": views,
            "post_view_counts": counts,
        }
    )
    override_client(app, fake)

    response = TestClient(app).post(
        "/api/posts/hello-world/view", json={"visitorId": "device-a"}
    )

    assert response.status_code == 200
    assert response.json() == {"slug": "hello-world", "viewCount": 7, "counted": False}


def test_view_is_bucketed_by_the_korean_calendar_day() -> None:
    app, _ = make_app()
    views = FakeQuery(FakeResponse([{"post_id": 1}]))
    fake = RoutingFakeClient(
        {
            "posts": FakeQuery(FakeResponse([{"id": 1}])),
            "post_views": views,
            "post_view_counts": FakeQuery(FakeResponse([counts_row(1)])),
        }
    )
    override_client(app, fake)

    TestClient(app).post("/api/posts/hello-world/view", json={"visitorId": "device-a"})

    assert views.upserted is not None
    assert views.upserted["viewed_on"] == datetime.now(KST).date().isoformat()
    assert KST == timezone(timedelta(hours=9))


def test_view_without_a_visitor_id_falls_back_to_the_request_origin() -> None:
    app, _ = make_app()
    views = FakeQuery(FakeResponse([{"post_id": 1}]))
    fake = RoutingFakeClient(
        {
            "posts": FakeQuery(FakeResponse([{"id": 1}])),
            "post_views": views,
            "post_view_counts": FakeQuery(FakeResponse([counts_row(1)])),
        }
    )
    override_client(app, fake)

    response = TestClient(app).post(
        "/api/posts/hello-world/view",
        headers={"X-Forwarded-For": "203.0.113.9, 70.41.3.18", "User-Agent": "probe"},
    )

    assert response.status_code == 200
    assert response.json()["counted"] is True
    assert views.upserted is not None
    visitor = views.upserted["visitor"]
    assert len(visitor) == 64
    assert "203.0.113.9" not in visitor
    assert "probe" not in visitor


def test_view_on_a_draft_post_is_not_found() -> None:
    app, _ = make_app()
    fake = RoutingFakeClient(
        {
            "posts": FakeQuery(FakeResponse([])),
            "post_views": FakeQuery(FakeResponse([])),
            "post_view_counts": FakeQuery(FakeResponse([])),
        }
    )
    override_client(app, fake)

    response = TestClient(app).post("/api/posts/secret/view")

    assert response.status_code == 404
    assert response.json()["code"] == "post_not_found"


def test_unknown_visitor_count_defaults_to_zero() -> None:
    app, _ = make_app()
    fake = RoutingFakeClient(
        {
            "posts": FakeQuery(FakeResponse([{"id": 1}])),
            "post_views": FakeQuery(FakeResponse([{"post_id": 1}])),
            "post_view_counts": FakeQuery(FakeResponse([])),
        }
    )
    override_client(app, fake)

    response = TestClient(app).post(
        "/api/posts/hello-world/view", json={"visitorId": "device-a"}
    )

    assert response.status_code == 200
    assert response.json()["viewCount"] == 0


def test_blank_visitor_id_is_rejected() -> None:
    app, _ = make_app()
    fake = RoutingFakeClient(
        {
            "posts": FakeQuery(FakeResponse([{"id": 1}])),
            "post_views": FakeQuery(FakeResponse([])),
            "post_view_counts": FakeQuery(FakeResponse([])),
        }
    )
    override_client(app, fake)

    response = TestClient(app).post(
        "/api/posts/hello-world/view", json={"visitorId": ""}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_posts_list_and_detail_carry_the_view_count() -> None:
    app, _ = make_app()
    fake = RoutingFakeClient(
        {
            "posts": FakeQuery(FakeResponse([sample_row()], count=1)),
            "post_view_counts": FakeQuery(FakeResponse([counts_row(42)])),
        }
    )
    override_client(app, fake)
    client = TestClient(app)

    assert client.get("/api/posts").json()["items"][0]["viewCount"] == 42
    assert client.get("/api/posts/hello-world").json()["viewCount"] == 42


def test_posts_without_recorded_views_report_zero() -> None:
    app, _ = make_app()
    fake = RoutingFakeClient(
        {
            "posts": FakeQuery(FakeResponse([sample_row()], count=1)),
            "post_view_counts": FakeQuery(FakeResponse([])),
        }
    )
    override_client(app, fake)

    assert TestClient(app).get("/api/posts").json()["items"][0]["viewCount"] == 0


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
        "SUPABASE_SECRET_KEY": "sb_secret_test",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_visitor_id_hash_is_stable_and_unique_per_device() -> None:
    settings = _settings()
    request = build_request([])

    first = resolve_visitor(settings, request, "device-a")
    again = resolve_visitor(settings, request, "device-a")
    other = resolve_visitor(settings, request, "device-b")

    assert first == again
    assert first != other
    assert first is not None and "device-a" not in first


def test_dedicated_salt_overrides_the_secret_key_for_visitor_hashing() -> None:
    request = build_request([])

    with_secret = resolve_visitor(_settings(), request, "device-a")
    with_salt = resolve_visitor(
        _settings(VIEW_HASH_SALT="separate-salt"), request, "device-a"
    )

    assert with_secret != with_salt


def test_request_without_any_identity_is_not_identified() -> None:
    settings = _settings()

    assert resolve_visitor(settings, build_request([]), None) is None


def test_visitor_is_not_identified_without_a_hashing_secret() -> None:
    settings = _settings(SUPABASE_SECRET_KEY=None)
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


def test_unidentifiable_request_is_not_recorded() -> None:
    from app.services.views import record_view

    views = FakeQuery(FakeResponse([]))
    fake = RoutingFakeClient(
        {
            "posts": FakeQuery(FakeResponse([{"id": 1}])),
            "post_views": views,
            "post_view_counts": FakeQuery(FakeResponse([counts_row(5)])),
        }
    )

    async def run() -> Any:
        return await record_view(fake, "hello-world", visitor=None)  # type: ignore[arg-type]

    import asyncio

    result = asyncio.run(run())

    assert result.counted is False
    assert result.view_count == 5
    assert views.upserted is None


def test_empty_list_page_skips_the_view_count_query() -> None:
    app, _ = make_app()
    fake = RoutingFakeClient(
        {
            "posts": FakeQuery(FakeResponse([], count=0)),
            "post_view_counts": FakeQuery(FakeResponse([])),
        }
    )
    override_client(app, fake)

    response = TestClient(app).get("/api/posts")

    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}
    assert "post_view_counts" not in fake.requested


def test_corrupt_view_total_is_reported_as_a_store_error() -> None:
    app, _ = make_app()
    fake = RoutingFakeClient(
        {
            "posts": FakeQuery(FakeResponse([sample_row()], count=1)),
            "post_view_counts": FakeQuery(FakeResponse([counts_row(-1)])),
        }
    )
    override_client(app, fake)

    response = TestClient(app).get("/api/posts/hello-world")

    assert response.status_code == 502
    assert response.json()["code"] == "database_response_invalid"
