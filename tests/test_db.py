import psycopg
import pytest
from psycopg import errors

from app.services.db import ensure_row, map_db_error


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (errors.UniqueViolation(), 409, "post_slug_exists"),
        (errors.InsufficientPrivilege(), 403, "database_access_denied"),
        (errors.InvalidTextRepresentation(), 422, "invalid_row"),
        (errors.UndefinedTable(), 404, "table_not_found"),
        (errors.UndefinedColumn(), 404, "column_not_found"),
        (errors.QueryCanceled(), 503, "database_unavailable"),
        (psycopg.OperationalError("private details"), 503, "database_unavailable"),
        (errors.CheckViolation(), 502, "database_request_failed"),
    ],
)
def test_database_errors_map_to_stable_public_codes(
    error: psycopg.Error, status: int, code: str
) -> None:
    mapped = map_db_error(error)

    assert (mapped.status_code, mapped.code) == (status, code)
    assert "private" not in mapped.message


def test_ensure_row_raises_not_found() -> None:
    with pytest.raises(Exception) as raised:
        ensure_row([], code="x_not_found", message="X was not found")

    assert getattr(raised.value, "status_code", None) == 404
