from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.config import Settings, get_settings
from app.core.visitor import resolve_visitor
from app.integrations.supabase import get_admin_client
from app.schemas import PostViewCreate, PostViewOut
from app.services import views
from supabase import AsyncClient

router = APIRouter(prefix="/posts", tags=["views"])
AdminClient = Annotated[AsyncClient, Depends(get_admin_client)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]


@router.post("/{slug}/view", response_model=PostViewOut, response_model_by_alias=True)
async def record_post_view(
    slug: str,
    request: Request,
    client: AdminClient,
    settings: CurrentSettings,
    view_input: PostViewCreate | None = None,
) -> PostViewOut:
    visitor = resolve_visitor(
        settings, request, view_input.visitor_id if view_input else None
    )
    return await views.record_view(client, slug, visitor=visitor)
