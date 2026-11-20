from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi import status as http_status

from app.core.config import Settings, get_settings
from app.integrations.postgres import get_db, require_blog_api_key
from app.schemas import PostCreate, PostList, PostLocale, PostOut, PostPatch, PostType
from app.services import posts
from app.services.db import Db

router = APIRouter(prefix="/posts", tags=["posts"])
AdminAuth = Annotated[None, Depends(require_blog_api_key)]
Conn = Annotated[Db, Depends(get_db)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]
BlogKey = Annotated[str | None, Header(alias="X-Blog-Key")]


@router.get("", response_model=PostList, response_model_by_alias=True)
async def list_posts(
    conn: Conn,
    settings: CurrentSettings,
    x_blog_key: BlogKey = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    post_type: Annotated[PostType | None, Query(alias="type")] = None,
    tag: Annotated[str | None, Query(max_length=80)] = None,
    locale: Annotated[PostLocale | None, Query()] = None,
    include_drafts: Annotated[bool, Query(alias="includeDrafts")] = False,
) -> PostList:
    if include_drafts:
        require_blog_api_key(settings, x_blog_key)
    return await posts.list_posts(
        conn,
        limit=limit,
        offset=offset,
        post_type=post_type,
        tag=tag,
        locale=locale,
        include_drafts=include_drafts,
    )


@router.post(
    "",
    response_model=PostOut,
    response_model_by_alias=True,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_post(
    post_input: PostCreate,
    _: AdminAuth,
    conn: Conn,
) -> PostOut:
    return await posts.create_post(conn, post_input)


@router.get("/{slug}", response_model=PostOut, response_model_by_alias=True)
async def get_post(
    slug: str,
    conn: Conn,
    settings: CurrentSettings,
    x_blog_key: BlogKey = None,
    include_drafts: Annotated[bool, Query(alias="includeDrafts")] = False,
) -> PostOut:
    if include_drafts:
        require_blog_api_key(settings, x_blog_key)
    return await posts.get_post(conn, slug, include_drafts=include_drafts)


@router.patch("/{slug}", response_model=PostOut, response_model_by_alias=True)
async def update_post(
    slug: str,
    post_input: PostPatch,
    _: AdminAuth,
    conn: Conn,
) -> PostOut:
    return await posts.update_post(conn, slug, post_input)


@router.delete("/{slug}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_post(
    slug: str,
    _: AdminAuth,
    conn: Conn,
) -> Response:
    return await posts.delete_post(conn, slug)
