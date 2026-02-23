from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.offers_repo import OffersRepo
from app.economy.offers.constants import OFFER_NOT_SHOW_DISMISS_REASON


async def dismiss_offer(
    session: AsyncSession,
    *,
    user_id: int,
    impression_id: int,
    now_utc: datetime,
) -> bool:
    return await OffersRepo.mark_dismissed(
        session,
        user_id=user_id,
        impression_id=impression_id,
        dismiss_reason=OFFER_NOT_SHOW_DISMISS_REASON,
        dismissed_at=now_utc,
    )


async def mark_offer_clicked(
    session: AsyncSession,
    *,
    user_id: int,
    impression_id: int,
    clicked_at: datetime,
) -> bool:
    return await OffersRepo.mark_clicked(
        session,
        user_id=user_id,
        impression_id=impression_id,
        clicked_at=clicked_at,
    )


async def mark_offer_converted_purchase(
    session: AsyncSession,
    *,
    user_id: int,
    impression_id: int,
    purchase_id: UUID,
) -> bool:
    return await OffersRepo.mark_converted_purchase(
        session,
        user_id=user_id,
        impression_id=impression_id,
        purchase_id=purchase_id,
    )
