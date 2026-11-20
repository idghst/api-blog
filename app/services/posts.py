from datetime import UTC, datetime
from typing import Any, LiteralString

from fastapi import Response
from fastapi import status as http_status
from psycopg import sql
from pydantic import ValidationError

from app.core.errors import ApiError
from app.schemas import PostCreate, PostList, PostLocale, PostOut, PostPatch, PostType
from app.services.db import Db, ensure_row, fetch, invalid_response

_NOT_FOUND = ("post_not_found", "Post was not found")
_PUBLISHED_AT = "published_at"


def _needs_publish_stamp(row: dict[str, Any]) -> bool:
    """A published post must carry the time it went live."""
    return row.get("draft") is False and row.get(_PUBLISHED_AT) is None


async def _stamp_published_at(conn: Db, slug: str) -> dict[str, Any] | None:
    """Fill an empty published_at. Returns None when another writer won the race."""
    rows = await fetch(
        conn,
        "update blog.posts set published_at = %s"
        " where slug = %s and published_at is null returning *",
        (datetime.now(UTC), slug),
    )
    return rows[0] if rows else None


def _as_nonneg_int(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise invalid_response()
    return value


async def published_post_id(conn: Db, slug: str) -> int:
    rows = await fetch(
        conn,
        "select id from blog.posts where slug = %s and draft = false limit 1",
        (slug,),
    )
    row = ensure_row(rows, code=_NOT_FOUND[0], message=_NOT_FOUND[1])
    return _as_nonneg_int(row.get("id"))


async def view_total(conn: Db, post_id: int) -> int:
    rows = await fetch(
        conn, "select total from blog.post_view_counts where post_id = %s", (post_id,)
    )
    return _as_nonneg_int(rows[0].get("total")) if rows else 0


async def view_totals(conn: Db, post_ids: list[int]) -> dict[int, int]:
    """페이지 전체 조회수를 한 번에 읽는다. 글마다 질의하면 N+1이 된다."""

    if not post_ids:
        return {}
    rows = await fetch(
        conn,
        "select post_id, total from blog.post_view_counts where post_id = any(%s)",
        (post_ids,),
    )
    return {
        _as_nonneg_int(row.get("post_id")): _as_nonneg_int(row.get("total"))
        for row in rows
    }


def _output(row: dict[str, Any], view_count: int = 0) -> PostOut:
    try:
        return PostOut.model_validate({**row, "view_count": view_count})
    except ValidationError as error:
        raise invalid_response() from error


async def list_posts(
    conn: Db,
    *,
    limit: int,
    offset: int,
    post_type: PostType | None = None,
    tag: str | None = None,
    locale: PostLocale | None = None,
    include_drafts: bool = False,
) -> PostList:
    conditions: list[LiteralString] = ["true"]
    params: list[Any] = []
    if not include_drafts:
        conditions.append("draft = false")
    if post_type is not None:
        conditions.append("type = %s")
        params.append(post_type)
    if tag:
        conditions.append("tags @> array[%s]::text[]")
        params.append(tag)
    if locale is not None:
        conditions.append("locale = %s")
        params.append(locale)
    where = sql.SQL(" and ").join(sql.SQL(c) for c in conditions)
    count_rows = await fetch(
        conn,
        sql.SQL("select count(*) as count from blog.posts where {}").format(where),
        params,
    )
    count = _as_nonneg_int(count_rows[0].get("count"))
    if offset > count:
        # PostgREST가 범위를 넘는 offset에 416을 주던 것이 502로 나가던 동작을 유지한다.
        raise ApiError(502, "database_request_failed", "Database request failed")
    rows = await fetch(
        conn,
        sql.SQL(
            "select * from blog.posts where {}"
            " order by published_at desc nulls last limit %s offset %s"
        ).format(where),
        [*params, limit, offset],
    )
    totals = await view_totals(conn, [_as_nonneg_int(row.get("id")) for row in rows])
    return PostList(
        items=[
            _output(row, totals.get(_as_nonneg_int(row.get("id")), 0)) for row in rows
        ],
        count=count,
    )


async def get_post(conn: Db, slug: str, *, include_drafts: bool = False) -> PostOut:
    rows = await fetch(
        conn,
        "select * from blog.posts where slug = %s and (%s or draft = false) limit 1",
        (slug, include_drafts),
    )
    row = ensure_row(rows, code=_NOT_FOUND[0], message=_NOT_FOUND[1])
    return _output(row, await view_total(conn, _as_nonneg_int(row.get("id"))))


async def create_post(conn: Db, post_input: PostCreate) -> PostOut:
    values = post_input.model_dump(exclude_none=True)
    if not post_input.draft and post_input.published_at is None:
        values[_PUBLISHED_AT] = datetime.now(UTC)
    rows = await fetch(
        conn,
        sql.SQL("insert into blog.posts ({}) values ({}) returning *").format(
            sql.SQL(", ").join(map(sql.Identifier, values)),
            sql.SQL(", ").join(sql.Placeholder() * len(values)),
        ),
        list(values.values()),
    )
    if not rows:
        raise invalid_response()
    return _output(rows[0])


async def update_post(conn: Db, slug: str, post_input: PostPatch) -> PostOut:
    changes = post_input.model_dump(exclude_unset=True)
    if not changes:
        raise ApiError(422, "validation_error", "Request validation failed")
    rows = await fetch(
        conn,
        sql.SQL("update blog.posts set {} where slug = %s returning *").format(
            sql.SQL(", ").join(
                sql.SQL("{} = %s").format(sql.Identifier(column)) for column in changes
            )
        ),
        [*changes.values(), slug],
    )
    row = ensure_row(rows, code=_NOT_FOUND[0], message=_NOT_FOUND[1])
    if _needs_publish_stamp(row):
        row = await _stamp_published_at(conn, row["slug"]) or row
    return _output(row, await view_total(conn, _as_nonneg_int(row.get("id"))))


async def delete_post(conn: Db, slug: str) -> Response:
    rows = await fetch(
        conn, "delete from blog.posts where slug = %s returning id", (slug,)
    )
    ensure_row(rows, code=_NOT_FOUND[0], message=_NOT_FOUND[1])
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
