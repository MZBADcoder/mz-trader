"""HTTP router registration."""

from fastapi import APIRouter

from api.routers.health import router as health_router


router = APIRouter()
router.include_router(health_router)
