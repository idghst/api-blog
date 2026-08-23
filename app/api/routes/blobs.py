from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi import status as http_status

from app.integrations.supabase import get_admin_client, require_blog_api_key
from app.schemas import BlobCreate, BlobMeta
from app.services import blobs
from supabase import AsyncClient

router = APIRouter(prefix="/blobs", tags=["blobs"])
AdminAuth = Annotated[None, Depends(require_blog_api_key)]
AdminClient = Annotated[AsyncClient, Depends(get_admin_client)]


@router.post(
    "",
    response_model=BlobMeta,
    response_model_by_alias=True,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_blob(
    blob_input: BlobCreate,
    _: AdminAuth,
    client: AdminClient,
) -> BlobMeta:
    return await blobs.create_blob(client, blob_input)


@router.get("/{blob_id}/meta", response_model=BlobMeta, response_model_by_alias=True)
async def get_blob_meta(blob_id: str, client: AdminClient) -> BlobMeta:
    return await blobs.get_blob_meta(client, blob_id)


@router.get("/{blob_id}")
async def get_blob(blob_id: str, client: AdminClient) -> Response:
    return await blobs.get_blob_bytes(client, blob_id)
