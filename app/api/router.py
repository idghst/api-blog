from fastapi import APIRouter

from app.api.routes.blobs import router as blobs_router
from app.api.routes.comments import router as comments_router
from app.api.routes.posts import router as posts_router

api_router = APIRouter(prefix="/api")
api_router.include_router(comments_router)
api_router.include_router(blobs_router)
api_router.include_router(posts_router)
