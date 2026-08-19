from collections.abc import AsyncIterator
from secrets import compare_digest
from typing import Annotated

import httpx
from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from supabase import AsyncClient, AsyncClientOptions, acreate_client


async def _new_client(
    settings: Settings, key: str
) -> tuple[AsyncClient, httpx.AsyncClient]:
    http_client = httpx.AsyncClient(timeout=settings.SUPABASE_TIMEOUT_SECONDS)
    try:
        client = await acreate_client(
            str(settings.SUPABASE_URL),
            key,
            options=AsyncClientOptions(
                schema=settings.supabase_schema,
                persist_session=False,
                auto_refresh_token=False,
                postgrest_client_timeout=settings.SUPABASE_TIMEOUT_SECONDS,
                httpx_client=http_client,
            ),
        )
    except Exception:
        await http_client.aclose()
        raise
    return client, http_client


def require_blog_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_blog_key: Annotated[str | None, Header(alias="X-Blog-Key")] = None,
) -> None:
    if settings.BLOG_API_KEY is None:
        raise ApiError(
            503,
            "administrator_authentication_unavailable",
            "Administrator authentication is unavailable",
        )

    if x_blog_key is None or not compare_digest(
        x_blog_key, settings.BLOG_API_KEY.get_secret_value()
    ):
        raise ApiError(
            401,
            "administrator_authentication_required",
            "Valid X-Blog-Key is required",
        )


async def get_admin_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[AsyncClient]:
    if settings.SUPABASE_SECRET_KEY is None:
        raise ApiError(
            503,
            "administrator_client_unavailable",
            "Administrator client is unavailable",
        )

    client, http_client = await _new_client(
        settings, settings.SUPABASE_SECRET_KEY.get_secret_value()
    )
    try:
        yield client
    finally:
        await http_client.aclose()
