from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.promo_repo import PromoRepo
from app.db.repo.users_repo import UsersRepo
from app.economy.promo.errors import (
    PromoIdempotencyConflictError,
    PromoInvalidError,
    PromoNotApplicableError,
    PromoUserNotFoundError,
)
from app.economy.promo.redeem_effects import reserve_discount_redemption
from app.economy.promo.service_redeem_context import (
    PromoRedeemDeps,
    PromoRedeemRuntime,
    ValidatedPromoRedemption,
    build_promo_redeem_runtime,
)
from app.economy.promo.service_redeem_prepare import prepare_validated_redemption
from app.economy.promo.types import PromoRedeemResult


async def _resolve_idempotent_redeem_result(
    runtime: PromoRedeemRuntime,
    *,
    deps: PromoRedeemDeps,
) -> PromoRedeemResult | None:
    existing = await PromoRepo.get_redemption_by_idempotency_key_for_update(
        runtime.session,
        runtime.idempotency_key,
    )
    if existing is None:
        return None
    if existing.user_id != runtime.user_id:
        raise PromoIdempotencyConflictError
    return await deps.build_idempotent_result(runtime.session, redemption=existing)


async def _ensure_redeem_user_exists(runtime: PromoRedeemRuntime) -> None:
    user = await UsersRepo.get_by_id(runtime.session, runtime.user_id)
    if user is None:
        raise PromoUserNotFoundError


async def _record_accepted_attempt(
    runtime: PromoRedeemRuntime,
    *,
    code_hash: str,
    redemption: PromoRedemption,
) -> None:
    await runtime.attempts.record_attempt(
        runtime.session,
        user_id=runtime.user_id,
        normalized_code_hash=code_hash,
        result="ACCEPTED",
        now_utc=runtime.now_utc,
        metadata={"redemption_id": str(redemption.id)},
    )


async def _apply_premium_grant_result(
    runtime: PromoRedeemRuntime,
    *,
    validated_redemption: ValidatedPromoRedemption,
    deps: PromoRedeemDeps,
) -> PromoRedeemResult:
    result = await deps.apply_premium_grant_redemption(
        runtime.session,
        user_id=runtime.user_id,
        redemption=validated_redemption.redemption,
        now_utc=runtime.now_utc,
        promo_code=validated_redemption.matched_code,
        apply_premium_grant=deps.apply_premium_grant,
    )
    await _record_accepted_attempt(
        runtime,
        code_hash=validated_redemption.code_hash,
        redemption=validated_redemption.redemption,
    )
    return result


async def _apply_discount_result(
    runtime: PromoRedeemRuntime,
    *,
    validated_redemption: ValidatedPromoRedemption,
) -> PromoRedeemResult:
    if (
        validated_redemption.matched_code.discount_type is None
        and validated_redemption.matched_code.discount_percent is None
    ):
        raise PromoNotApplicableError

    await _record_accepted_attempt(
        runtime,
        code_hash=validated_redemption.code_hash,
        redemption=validated_redemption.redemption,
    )
    return reserve_discount_redemption(
        redemption=validated_redemption.redemption,
        promo_code=validated_redemption.matched_code,
        now_utc=runtime.now_utc,
    )


async def _apply_redeem_result(
    runtime: PromoRedeemRuntime,
    *,
    validated_redemption: ValidatedPromoRedemption,
    deps: PromoRedeemDeps,
) -> PromoRedeemResult:
    if validated_redemption.matched_code.promo_type == "PREMIUM_GRANT":
        return await _apply_premium_grant_result(
            runtime,
            validated_redemption=validated_redemption,
            deps=deps,
        )
    if validated_redemption.matched_code.promo_type == "PERCENT_DISCOUNT":
        return await _apply_discount_result(
            runtime,
            validated_redemption=validated_redemption,
        )
    raise PromoInvalidError


async def redeem_promo_code(
    session: AsyncSession,
    *,
    user_id: int,
    promo_code: str,
    idempotency_key: str,
    source: str,
    now_utc: datetime | None,
    deps: PromoRedeemDeps,
) -> PromoRedeemResult:
    runtime = build_promo_redeem_runtime(
        session,
        user_id=user_id,
        idempotency_key=idempotency_key,
        source=source,
        now_utc=now_utc,
        deps=deps,
    )
    idempotent_result = await _resolve_idempotent_redeem_result(runtime, deps=deps)
    if idempotent_result is not None:
        return idempotent_result

    await _ensure_redeem_user_exists(runtime)
    validated_redemption = await prepare_validated_redemption(
        runtime,
        promo_code=promo_code,
        deps=deps,
    )
    return await _apply_redeem_result(
        runtime,
        validated_redemption=validated_redemption,
        deps=deps,
    )
