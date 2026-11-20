from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi import status as http_status

from app.integrations.postgres import get_db, require_blog_api_key
from app.schemas import BlobCreate, BlobMeta
from app.services import blobs
from app.services.db import Db

router = APIRouter(prefix="/blobs", tags=["blobs"])
AdminAuth = Annotated[None, Depends(require_blog_api_key)]
Conn = Annotated[Db, Depends(get_db)]


@router.post(
    "",
    response_model=BlobMeta,
    response_model_by_alias=True,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_blob(
    blob_input: BlobCreate,
    _: AdminAuth,
    conn: Conn,
) -> BlobMeta:
    return await blobs.create_blob(conn, blob_input)


@router.get("/{blob_id}/meta", response_model=BlobMeta, response_model_by_alias=True)
async def get_blob_meta(blob_id: str, conn: Conn) -> BlobMeta:
    return await blobs.get_blob_meta(conn, blob_id)


@router.get("/{blob_id}")
async def get_blob(blob_id: str, conn: Conn) -> Response:
    return await blobs.get_blob_bytes(conn, blob_id)
