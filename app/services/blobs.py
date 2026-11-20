from base64 import b64decode
from binascii import Error as BinasciiError
from typing import Any

from fastapi import Response
from pydantic import ValidationError

from app.core.errors import ApiError
from app.schemas import BlobCreate, BlobMeta
from app.services.db import Db, ensure_row, fetch, invalid_response

_META_COLUMNS = "id::text as id, description, mime_type, created_at"
_NOT_FOUND = ("blob_not_found", "Blob was not found")
_MAX_BYTES = 2_000_000


def _meta(row: dict[str, Any]) -> BlobMeta:
    try:
        return BlobMeta.model_validate(row)
    except ValidationError as error:
        raise invalid_response() from error


def decode_bytea(value: object) -> bytes:
    if not isinstance(value, bytes):
        raise invalid_response()
    return value


def _raw_bytes(content_base64: str) -> bytes:
    try:
        data = b64decode(content_base64, validate=True)
    except (BinasciiError, ValueError) as error:
        raise ApiError(422, "validation_error", "Request validation failed") from error
    if not data or len(data) > _MAX_BYTES:
        raise ApiError(422, "validation_error", "Request validation failed")
    return data


async def create_blob(conn: Db, blob_input: BlobCreate) -> BlobMeta:
    raw = _raw_bytes(blob_input.content_base64)
    rows = await fetch(
        conn,
        "insert into blog.blobs (description, mime_type, bytes)"
        f" values (%s, %s, %s) returning {_META_COLUMNS}",
        (blob_input.description, blob_input.mime_type, raw),
    )
    if not rows:
        raise invalid_response()
    return _meta(rows[0])


async def _load(conn: Db, blob_id: str) -> dict[str, Any]:
    rows = await fetch(
        conn,
        f"select {_META_COLUMNS}, bytes from blog.blobs where id = %s limit 1",
        (blob_id,),
    )
    return ensure_row(rows, code=_NOT_FOUND[0], message=_NOT_FOUND[1])


async def get_blob_meta(conn: Db, blob_id: str) -> BlobMeta:
    return _meta(await _load(conn, blob_id))


async def get_blob_bytes(conn: Db, blob_id: str) -> Response:
    row = await _load(conn, blob_id)
    meta = _meta(row)
    return Response(content=decode_bytea(row.get("bytes")), media_type=meta.mime_type)
