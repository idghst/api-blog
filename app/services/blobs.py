from base64 import b64decode
from binascii import Error as BinasciiError
from typing import Any

from fastapi import Response
from pydantic import ValidationError

from app.core.errors import ApiError
from app.schemas import BlobCreate, BlobMeta
from app.services.postgrest import ensure_row, execute_query, invalid_response
from supabase import AsyncClient

TABLE_NAME = "blobs"
_NOT_FOUND = ("blob_not_found", "Blob was not found")
_MAX_BYTES = 2_000_000


def _meta(row: dict[str, Any]) -> BlobMeta:
    try:
        return BlobMeta.model_validate(row)
    except ValidationError as error:
        raise invalid_response() from error


def decode_bytea(value: object) -> bytes:
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, str) and value.startswith("\\x"):
        try:
            return bytes.fromhex(value[2:])
        except ValueError as error:
            raise invalid_response() from error
    raise invalid_response()


def _raw_bytes(content_base64: str) -> bytes:
    try:
        data = b64decode(content_base64, validate=True)
    except (BinasciiError, ValueError) as error:
        raise ApiError(422, "validation_error", "Request validation failed") from error
    if not data or len(data) > _MAX_BYTES:
        raise ApiError(422, "validation_error", "Request validation failed")
    return data


async def create_blob(client: AsyncClient, blob_input: BlobCreate) -> BlobMeta:
    raw = _raw_bytes(blob_input.content_base64)
    rows, _ = await execute_query(
        client.table(TABLE_NAME).insert(
            {
                "description": blob_input.description,
                "mime_type": blob_input.mime_type,
                "bytes": "\\x" + raw.hex(),
            }
        )
    )
    if not rows:
        raise invalid_response()
    return _meta(rows[0])


async def _load(client: AsyncClient, blob_id: str) -> dict[str, Any]:
    rows, _ = await execute_query(
        client.table(TABLE_NAME).select("*").eq("id", blob_id).limit(1)
    )
    return ensure_row(rows, code=_NOT_FOUND[0], message=_NOT_FOUND[1])


async def get_blob_meta(client: AsyncClient, blob_id: str) -> BlobMeta:
    return _meta(await _load(client, blob_id))


async def get_blob_bytes(client: AsyncClient, blob_id: str) -> Response:
    row = await _load(client, blob_id)
    meta = _meta(row)
    return Response(content=decode_bytea(row.get("bytes")), media_type=meta.mime_type)
