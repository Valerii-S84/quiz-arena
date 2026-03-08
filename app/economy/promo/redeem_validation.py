from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.purchases_repo import PurchasesRepo
from app.economy.promo.errors import (
    PromoAlreadyUsedError,
    PromoExpiredError,
    PromoNotApplicableError,
)
from app.economy.promo.retry_policy import can_user_retry_promo

FailedAttemptWriter = Callable[..., Awaitable[None]]


async def ensure_retry_allowed(
    *,
    redemptions: Sequence[PromoRedemption],
    promo_code: PromoCode,
    user_id: int,
    code_hash: str,
    now_utc: datetime,
    record_failed_attempt: FailedAttemptWriter,
) -> None:
    if can_user_retry_promo(
        redemptions=redemptions,
        max_uses_per_user=promo_code.max_uses_per_user,
    ):
        return
    await record_failed_attempt(
        user_id=user_id,
        normalized_code_hash=code_hash,
        result="NOT_APPLICABLE",
        now_utc=now_utc,
        metadata={
            "reason": "ALREADY_USED",
            "max_uses_per_user": promo_code.max_uses_per_user,
            "previous_redemptions": len(redemptions),
        },
    )
    raise PromoAlreadyUsedError


async def ensure_code_is_current(
    *,
    promo_code: PromoCode,
    user_id: int,
    code_hash: str,
    now_utc: datetime,
    record_failed_attempt: FailedAttemptWriter,
) -> None:
    if promo_code.status != "ACTIVE" or not (
        promo_code.valid_from <= now_utc < promo_code.valid_until
    ):
        await record_failed_attempt(
            user_id=user_id,
            normalized_code_hash=code_hash,
            result="EXPIRED",
            now_utc=now_utc,
        )
        raise PromoExpiredError
    if promo_code.max_total_uses is None or promo_code.used_total < promo_code.max_total_uses:
        return
    await record_failed_attempt(
        user_id=user_id,
        normalized_code_hash=code_hash,
        result="EXPIRED",
        now_utc=now_utc,
        metadata={"reason": "DEPLETED"},
    )
    raise PromoExpiredError


async def ensure_purchase_eligibility(
    session: AsyncSession,
    *,
    promo_code: PromoCode,
    user_id: int,
    code_hash: str,
    now_utc: datetime,
    record_failed_attempt: FailedAttemptWriter,
) -> None:
    if not promo_code.new_users_only and not promo_code.first_purchase_only:
        return
    purchase_count = await PurchasesRepo.count_by_user(session, user_id=user_id)
    if promo_code.new_users_only and purchase_count > 0:
        await record_failed_attempt(
            user_id=user_id,
            normalized_code_hash=code_hash,
            result="NOT_APPLICABLE",
            now_utc=now_utc,
            metadata={"reason": "NEW_USERS_ONLY"},
        )
        raise PromoNotApplicableError
    if promo_code.first_purchase_only and purchase_count > 0:
        await record_failed_attempt(
            user_id=user_id,
            normalized_code_hash=code_hash,
            result="NOT_APPLICABLE",
            now_utc=now_utc,
            metadata={"reason": "FIRST_PURCHASE_ONLY"},
        )
        raise PromoNotApplicableError
