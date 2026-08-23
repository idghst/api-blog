from typing import Any

from postgrest.types import CountMethod
from pydantic import ValidationError

from app.schemas import CommentCreate, CommentList, CommentOut
from app.services.postgrest import ensure_row, execute_query, invalid_response
from supabase import AsyncClient

POSTS_TABLE = "posts"
TABLE_NAME = "comments"
_POST_NOT_FOUND = ("post_not_found", "Post was not found")


def _output(row: dict[str, Any]) -> CommentOut:
    try:
        return CommentOut.model_validate(row)
    except ValidationError as error:
        raise invalid_response() from error


async def _published_post_id(client: AsyncClient, slug: str) -> int:
    rows, _ = await execute_query(
        client.table(POSTS_TABLE)
        .select("id")
        .eq("slug", slug)
        .eq("draft", False)
        .limit(1)
    )
    row = ensure_row(rows, code=_POST_NOT_FOUND[0], message=_POST_NOT_FOUND[1])
    post_id = row.get("id")
    if not isinstance(post_id, int) or isinstance(post_id, bool):
        raise invalid_response()
    return post_id


async def list_comments(client: AsyncClient, slug: str) -> CommentList:
    post_id = await _published_post_id(client, slug)
    rows, count = await execute_query(
        client.table(TABLE_NAME)
        .select("*", count=CountMethod.exact)
        .eq("post_id", post_id)
        .order("created_at", desc=False)
    )
    if count is None:
        raise invalid_response()
    return CommentList(items=[_output(row) for row in rows], count=count)


async def create_comment(
    client: AsyncClient, slug: str, comment_input: CommentCreate
) -> CommentOut:
    post_id = await _published_post_id(client, slug)
    rows, _ = await execute_query(
        client.table(TABLE_NAME).insert(
            {
                "post_id": post_id,
                "author": comment_input.author,
                "body": comment_input.body,
            }
        )
    )
    if not rows:
        raise invalid_response()
    return _output(rows[0])
