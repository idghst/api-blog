from collections.abc import AsyncIterator
from secrets import compare_digest
from typing import Annotated

import psycopg
from fastapi import Depends, Header
from psycopg.rows import dict_row

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.services.db import Db, map_db_error


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


async def connect(settings: Settings) -> Db:
    timeout_ms = settings.DB_TIMEOUT_SECONDS * 1000
    try:
        return await psycopg.AsyncConnection.connect(
            settings.DATABASE_URL.get_secret_value(),
            autocommit=True,
            row_factory=dict_row,
            connect_timeout=settings.DB_TIMEOUT_SECONDS,
            # 응답의 시각은 Supabase 때처럼 UTC로 직렬화한다.
            options=f"-c TimeZone=UTC -c statement_timeout={timeout_ms}",
        )
    except psycopg.Error as error:
        raise map_db_error(error) from error


async def get_db(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[Db]:
    # shortcut: 요청마다 새 연결. 동시 요청이 많아지면 psycopg_pool로 바꾼다.
    async with await connect(settings) as conn:
        yield conn
