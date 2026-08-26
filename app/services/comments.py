from typing import Any

from postgrest.types import CountMethod
from pydantic import ValidationError

from app.schemas import CommentCreate, CommentList, CommentOut
from app.services.postgrest import execute_query, invalid_response
from app.services.posts import published_post_id
from supabase import AsyncClient

TABLE_NAME = "comments"


def _output(row: dict[str, Any]) -> CommentOut:
    try:
        return CommentOut.model_validate(row)
    except ValidationError as error:
        raise invalid_response() from error


async def list_comments(client: AsyncClient, slug: str) -> CommentList:
    post_id = await published_post_id(client, slug)
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
    post_id = await published_post_id(client, slug)
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
