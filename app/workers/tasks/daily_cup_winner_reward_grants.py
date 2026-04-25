from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.db.repo.ledger_repo import LedgerRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.economy.energy.service import EnergyService
from app.economy.premium_grants import grant_premium_days
from app.economy.purchases.catalog import get_product
from app.economy.purchases.service import PurchaseService
from app.game.sessions.service.constants import FRIEND_CHALLENGE_TICKET_PRODUCT_CODE

DAILY_CUP_PREMIUM_REWARD_DAYS = 3
DAILY_CUP_TICKET_REWARD_TOTAL = 2
DAILY_CUP_FREE_ENERGY_REWARD = 5


def _reward_key(
    *,
    prefix: str,
    tournament_id: UUID,
    user_id: int,
    suffix: int | None = None,
) -> str:
    parts = [prefix, tournament_id.hex, str(user_id)]
    if suffix is not None:
        parts.append(str(suffix))
    return ":".join(parts)


async def grant_daily_cup_rank_reward(
    *,
    session: Any,
    tournament_id: UUID,
    user_id: int,
    rank: int,
    now_utc: datetime,
    logger: Any,
) -> bool:
    try:
        async with session.begin_nested():
            if rank == 1:
                ledger_key = _reward_key(
                    prefix="dcpl",
                    tournament_id=tournament_id,
                    user_id=user_id,
                )
                if await LedgerRepo.get_by_idempotency_key(session, ledger_key) is None:
                    await grant_premium_days(
                        session,
                        user_id=user_id,
                        grant_days=DAILY_CUP_PREMIUM_REWARD_DAYS,
                        scope="PREMIUM_3_DAYS",
                        now_utc=now_utc,
                        source="TOURNAMENT",
                        entry_type="TOURNAMENT_REWARD",
                        entitlement_idempotency_key=_reward_key(
                            prefix="dcpe",
                            tournament_id=tournament_id,
                            user_id=user_id,
                        ),
                        ledger_idempotency_key=ledger_key,
                        metadata={
                            "rank": 1,
                            "reward_type": "PREMIUM_3_DAYS",
                            "tournament_id": str(tournament_id),
                        },
                    )
                return True

            if rank == 2:
                product = get_product(FRIEND_CHALLENGE_TICKET_PRODUCT_CODE)
                if product is None:
                    raise ValueError(
                        f"product is not configured: {FRIEND_CHALLENGE_TICKET_PRODUCT_CODE}"
                    )
                for ticket_no in range(1, DAILY_CUP_TICKET_REWARD_TOTAL + 1):
                    idempotency_key = _reward_key(
                        prefix="dctk",
                        tournament_id=tournament_id,
                        user_id=user_id,
                        suffix=ticket_no,
                    )
                    purchase = await PurchasesRepo.get_by_idempotency_key(session, idempotency_key)
                    if purchase is None:
                        purchase = PurchaseService._build_purchase(
                            product,
                            user_id=user_id,
                            idempotency_key=idempotency_key,
                            discount_stars_amount=product.stars_amount,
                            applied_promo_code_id=None,
                            now_utc=now_utc,
                        )
                        await PurchasesRepo.create(session, purchase=purchase, created_at=now_utc)
                    await PurchaseService.apply_zero_cost_purchase(
                        session,
                        purchase_id=purchase.id,
                        user_id=user_id,
                        now_utc=now_utc,
                    )
                return True

            result = await EnergyService.credit_paid_energy(
                session,
                user_id=user_id,
                amount=DAILY_CUP_FREE_ENERGY_REWARD,
                idempotency_key=_reward_key(
                    prefix="dcen",
                    tournament_id=tournament_id,
                    user_id=user_id,
                ),
                now_utc=now_utc,
                source="TOURNAMENT",
            )
            return result.amount > 0
    except Exception as exc:
        logger.warning(
            "daily_cup_winner_reward_grant_failed",
            tournament_id=str(tournament_id),
            user_id=user_id,
            rank=rank,
            error_type=type(exc).__name__,
        )
        return False
