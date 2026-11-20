from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi import status as http_status

from app.integrations.postgres import get_db
from app.schemas import CommentCreate, CommentList, CommentOut
from app.services import comments
from app.services.db import Db

router = APIRouter(prefix="/posts", tags=["comments"])
Conn = Annotated[Db, Depends(get_db)]


@router.get(
    "/{slug}/comments", response_model=CommentList, response_model_by_alias=True
)
async def list_comments(slug: str, conn: Conn) -> CommentList:
    return await comments.list_comments(conn, slug)


@router.post(
    "/{slug}/comments",
    response_model=CommentOut,
    response_model_by_alias=True,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_comment(
    slug: str,
    comment_input: CommentCreate,
    conn: Conn,
) -> CommentOut:
    return await comments.create_comment(conn, slug, comment_input)
