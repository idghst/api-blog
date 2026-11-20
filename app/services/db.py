from typing import Any, LiteralString

import psycopg
from psycopg import sql

from app.core.errors import ApiError

type Db = psycopg.AsyncConnection[dict[str, Any]]

_DEFAULT_ERRORS: dict[str, tuple[int, str, str]] = {
    "42P01": (404, "table_not_found", "Table not found"),
    "42703": (404, "column_not_found", "Column not found"),
    "22P02": (422, "invalid_row", "Row data is invalid"),
    "23505": (409, "post_slug_exists", "Post slug already exists"),
    "42501": (403, "database_access_denied", "Database access was denied"),
    "57014": (503, "database_unavailable", "Database is unavailable"),
}


def map_db_error(error: psycopg.Error) -> ApiError:
    mapped = _DEFAULT_ERRORS.get(error.sqlstate or "")
    if mapped is not None:
        return ApiError(*mapped)
    if isinstance(error, psycopg.OperationalError):
        return ApiError(503, "database_unavailable", "Database is unavailable")
    return ApiError(502, "database_request_failed", "Database request failed")


def invalid_response() -> ApiError:
    return ApiError(
        502,
        "database_response_invalid",
        "Database returned an invalid response",
    )


def ensure_row(
    rows: list[dict[str, Any]],
    *,
    code: str,
    message: str,
) -> dict[str, Any]:
    if not rows:
        raise ApiError(404, code, message)
    return rows[0]


async def fetch(
    conn: Db, query: LiteralString | sql.Composed, params: Any = None
) -> list[dict[str, Any]]:
    try:
        cursor = await conn.execute(query, params)
        return await cursor.fetchall() if cursor.description else []
    except psycopg.Error as error:
        raise map_db_error(error) from error
