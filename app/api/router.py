from fastapi import APIRouter

from app.api.routes.posts import router as posts_router

api_router = APIRouter(prefix="/api")
api_router.include_router(posts_router)
