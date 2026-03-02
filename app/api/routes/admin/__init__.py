from __future__ import annotations

from fastapi import APIRouter

from .auth import router as auth_router
from .content import router as content_router
from .economy import router as economy_router
from .overview import router as overview_router
from .promo import router as promo_router
from .system import router as system_router
from .users import router as users_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(overview_router)
router.include_router(economy_router)
router.include_router(users_router)
router.include_router(promo_router)
router.include_router(content_router)
router.include_router(system_router)

__all__ = ["router"]
