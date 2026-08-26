from datetime import UTC, datetime
from typing import Any

from fastapi import Response
from fastapi import status as http_status
from postgrest.types import CountMethod
from pydantic import ValidationError

from app.core.errors import ApiError
from app.schemas import PostCreate, PostList, PostLocale, PostOut, PostPatch, PostType
from app.services.postgrest import ensure_row, execute_query, invalid_response
from supabase import AsyncClient

TABLE_NAME = "posts"
_NOT_FOUND = ("post_not_found", "Post was not found")
_PUBLISHED_AT = "published_at"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _needs_publish_stamp(row: dict[str, Any]) -> bool:
    """A published post must carry the time it went live."""
    return row.get("draft") is False and row.get(_PUBLISHED_AT) is None


async def _stamp_published_at(client: AsyncClient, slug: str) -> dict[str, Any] | None:
    """Fill an empty published_at. Returns None when another writer won the race."""
    rows, _ = await execute_query(
        client.table(TABLE_NAME)
        .update({_PUBLISHED_AT: _now_iso()})
        .eq("slug", slug)
        .is_(_PUBLISHED_AT, None)
    )
    return rows[0] if rows else None


def _output(row: dict[str, Any]) -> PostOut:
    try:
        return PostOut.model_validate(row)
    except ValidationError as error:
        raise invalid_response() from error


async def list_posts(
    client: AsyncClient,
    *,
    limit: int,
    offset: int,
    post_type: PostType | None = None,
    tag: str | None = None,
    locale: PostLocale | None = None,
    include_drafts: bool = False,
) -> PostList:
    query = client.table(TABLE_NAME).select("*", count=CountMethod.exact)
    if not include_drafts:
        query = query.eq("draft", False)
    if post_type is not None:
        query = query.eq("type", post_type)
    if tag:
        query = query.contains("tags", [tag])
    if locale is not None:
        query = query.eq("locale", locale)
    rows, count = await execute_query(
        query.order(_PUBLISHED_AT, desc=True, nullsfirst=False).range(
            offset, offset + limit - 1
        )
    )
    if count is None:
        raise invalid_response()
    return PostList(items=[_output(row) for row in rows], count=count)


async def get_post(
    client: AsyncClient, slug: str, *, include_drafts: bool = False
) -> PostOut:
    query = client.table(TABLE_NAME).select("*").eq("slug", slug)
    if not include_drafts:
        query = query.eq("draft", False)
    rows, _ = await execute_query(query.limit(1))
    return _output(ensure_row(rows, code=_NOT_FOUND[0], message=_NOT_FOUND[1]))


async def create_post(client: AsyncClient, post_input: PostCreate) -> PostOut:
    values = post_input.model_dump(mode="json", exclude_none=True)
    if not post_input.draft and post_input.published_at is None:
        values[_PUBLISHED_AT] = _now_iso()
    rows, _ = await execute_query(client.table(TABLE_NAME).insert(values))
    if not rows:
        raise invalid_response()
    return _output(rows[0])


async def update_post(client: AsyncClient, slug: str, post_input: PostPatch) -> PostOut:
    changes = post_input.model_dump(exclude_unset=True, mode="json")
    if not changes:
        raise ApiError(422, "validation_error", "Request validation failed")
    rows, _ = await execute_query(
        client.table(TABLE_NAME).update(changes).eq("slug", slug)
    )
    row = ensure_row(rows, code=_NOT_FOUND[0], message=_NOT_FOUND[1])
    if _needs_publish_stamp(row):
        row = await _stamp_published_at(client, row["slug"]) or row
    return _output(row)


async def delete_post(client: AsyncClient, slug: str) -> Response:
    rows, _ = await execute_query(client.table(TABLE_NAME).delete().eq("slug", slug))
    ensure_row(rows, code=_NOT_FOUND[0], message=_NOT_FOUND[1])
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
