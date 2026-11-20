from typing import Any

from pydantic import ValidationError

from app.schemas import CommentCreate, CommentList, CommentOut
from app.services.db import Db, fetch, invalid_response
from app.services.posts import published_post_id


def _output(row: dict[str, Any]) -> CommentOut:
    try:
        return CommentOut.model_validate(row)
    except ValidationError as error:
        raise invalid_response() from error


async def list_comments(conn: Db, slug: str) -> CommentList:
    post_id = await published_post_id(conn, slug)
    rows = await fetch(
        conn,
        "select * from blog.comments where post_id = %s order by created_at",
        (post_id,),
    )
    return CommentList(items=[_output(row) for row in rows], count=len(rows))


async def create_comment(
    conn: Db, slug: str, comment_input: CommentCreate
) -> CommentOut:
    post_id = await published_post_id(conn, slug)
    rows = await fetch(
        conn,
        "insert into blog.comments (post_id, author, body)"
        " values (%s, %s, %s) returning *",
        (post_id, comment_input.author, comment_input.body),
    )
    if not rows:
        raise invalid_response()
    return _output(rows[0])
