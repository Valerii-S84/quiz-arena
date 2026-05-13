from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .constants import FRIEND_CHALLENGE_TICKET_PRODUCT_CODE


@dataclass(frozen=True, slots=True)
class DailyTicketRewardDeps:
    purchase_service_factory: Any
    product_lookup: Any
    purchases_repo: Any
    idempotency_key_builder: Any


async def credit_daily_duel_ticket(
    session: AsyncSession,
    *,
    user_id: int,
    daily_run_id: UUID,
    now_utc: datetime,
    deps: DailyTicketRewardDeps,
) -> None:
    purchase_service = deps.purchase_service_factory()
    purchase_idempotency_key = deps.idempotency_key_builder(daily_run_id=daily_run_id)
    purchase = await deps.purchases_repo.get_by_idempotency_key(session, purchase_idempotency_key)
    if purchase is None:
        product = deps.product_lookup(FRIEND_CHALLENGE_TICKET_PRODUCT_CODE)
        if product is None:
            raise ValueError("friend challenge ticket product is not configured")
        purchase = purchase_service._build_purchase(
            product,
            user_id=user_id,
            idempotency_key=purchase_idempotency_key,
            discount_stars_amount=product.stars_amount,
            applied_promo_code_id=None,
            now_utc=now_utc,
        )
        await deps.purchases_repo.create(session, purchase=purchase, created_at=now_utc)

    await purchase_service.apply_zero_cost_purchase(
        session,
        purchase_id=purchase.id,
        user_id=user_id,
        now_utc=now_utc,
    )
