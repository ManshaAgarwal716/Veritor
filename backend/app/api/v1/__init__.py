from fastapi import APIRouter

from app.api.v1 import scans, watchlist

router = APIRouter(prefix="/api/v1")
router.include_router(scans.router)
router.include_router(watchlist.router)
