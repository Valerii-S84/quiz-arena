from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin import users_bonus as _users_bonus
from app.api.routes.admin.users_listing import _build_search_filters, list_users_page
from app.api.routes.admin.users_profile import get_user_profile


async def apply_bonus(
    session: AsyncSession, *, user_id: int, bonus_type: str, amount: int
) -> dict[str, object]:
    setattr(_users_bonus, "datetime", datetime)
    return await _users_bonus.apply_bonus(
        session,
        user_id=user_id,
        bonus_type=bonus_type,
        amount=amount,
    )

__all__ = ["_build_search_filters", "apply_bonus", "get_user_profile", "list_users_page"]
