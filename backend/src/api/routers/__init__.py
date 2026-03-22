"""HTTP router registration."""

from fastapi import APIRouter

from api.routers.auth import router as auth_router
from api.routers.health import router as health_router
from api.routers.reference import router as reference_router
from api.routers.watchlist import router as watchlist_router


router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(health_router)
router.include_router(reference_router)
router.include_router(watchlist_router)
