from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi import status as http_status

from app.integrations.supabase import get_admin_client
from app.schemas import CommentCreate, CommentList, CommentOut
from app.services import comments
from supabase import AsyncClient

router = APIRouter(prefix="/posts", tags=["comments"])
AdminClient = Annotated[AsyncClient, Depends(get_admin_client)]


@router.get(
    "/{slug}/comments", response_model=CommentList, response_model_by_alias=True
)
async def list_comments(slug: str, client: AdminClient) -> CommentList:
    return await comments.list_comments(client, slug)


@router.post(
    "/{slug}/comments",
    response_model=CommentOut,
    response_model_by_alias=True,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_comment(
    slug: str,
    comment_input: CommentCreate,
    client: AdminClient,
) -> CommentOut:
    return await comments.create_comment(client, slug, comment_input)
