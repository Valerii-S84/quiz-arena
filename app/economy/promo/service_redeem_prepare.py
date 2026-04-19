from __future__ import annotations

from uuid import uuid4

from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.promo_repo import PromoRepo
from app.economy.promo.errors import PromoInvalidError, PromoRateLimitedError
from app.economy.promo.redeem_effects import build_validation_snapshot
from app.economy.promo.service_redeem_context import (
    PromoCodeLookup,
    PromoRedeemDeps,
    PromoRedeemRuntime,
    ValidatedPromoRedemption,
    build_promo_code_lookup,
)


async def _record_invalid_code_and_raise(
    runtime: PromoRedeemRuntime,
    *,
    code_hash: str,
    metadata: dict[str, object] | None = None,
) -> None:
    await runtime.attempts.record_failed_attempt(
        user_id=runtime.user_id,
        normalized_code_hash=code_hash,
        result="INVALID",
        now_utc=runtime.now_utc,
        metadata=metadata,
    )
    raise PromoInvalidError


async def _enforce_redeem_rate_limit(
    runtime: PromoRedeemRuntime,
    *,
    code_lookup: PromoCodeLookup,
    deps: PromoRedeemDeps,
) -> None:
    try:
        await deps.enforce_rate_limit(
            runtime.session,
            user_id=runtime.user_id,
            now_utc=runtime.now_utc,
        )
    except PromoRateLimitedError:
        await runtime.attempts.record_failed_attempt(
            user_id=runtime.user_id,
            normalized_code_hash=code_lookup.code_hash,
            result="RATE_LIMITED",
            now_utc=runtime.now_utc,
            metadata={"idempotency_key": runtime.idempotency_key},
        )
        raise


async def _resolve_matched_promo_code(
    runtime: PromoRedeemRuntime,
    *,
    code_lookup: PromoCodeLookup,
):
    if not code_lookup.normalized_code:
        await _record_invalid_code_and_raise(
            runtime,
            code_hash=code_lookup.code_hash,
            metadata={"reason": "EMPTY"},
        )

    matched_code = await PromoRepo.get_code_by_hash_for_update(
        runtime.session,
        code_lookup.code_hash,
    )
    if matched_code is None:
        await _record_invalid_code_and_raise(runtime, code_hash=code_lookup.code_hash)
    return matched_code


async def _validate_matched_promo_code(
    runtime: PromoRedeemRuntime,
    *,
    matched_code,
    code_lookup: PromoCodeLookup,
    deps: PromoRedeemDeps,
) -> None:
    previous_redemptions = await PromoRepo.list_redemptions_by_code_and_user_for_update(
        runtime.session,
        promo_code_id=matched_code.id,
        user_id=runtime.user_id,
    )
    await deps.ensure_retry_allowed(
        redemptions=previous_redemptions,
        promo_code=matched_code,
        user_id=runtime.user_id,
        code_hash=code_lookup.code_hash,
        now_utc=runtime.now_utc,
        record_failed_attempt=runtime.attempts.record_failed_attempt,
    )
    await deps.ensure_code_is_current(
        promo_code=matched_code,
        user_id=runtime.user_id,
        code_hash=code_lookup.code_hash,
        now_utc=runtime.now_utc,
        record_failed_attempt=runtime.attempts.record_failed_attempt,
    )
    await deps.ensure_purchase_eligibility(
        runtime.session,
        promo_code=matched_code,
        user_id=runtime.user_id,
        code_hash=code_lookup.code_hash,
        now_utc=runtime.now_utc,
        record_failed_attempt=runtime.attempts.record_failed_attempt,
    )


async def _create_validated_redemption(
    runtime: PromoRedeemRuntime,
    *,
    matched_code,
) -> PromoRedemption:
    return await PromoRepo.create_redemption(
        runtime.session,
        redemption=PromoRedemption(
            id=uuid4(),
            promo_code_id=matched_code.id,
            user_id=runtime.user_id,
            status="VALIDATED",
            reject_reason=None,
            reserved_until=None,
            applied_purchase_id=None,
            grant_entitlement_id=None,
            idempotency_key=runtime.idempotency_key,
            validation_snapshot=build_validation_snapshot(
                promo_code=matched_code,
                now_utc=runtime.now_utc,
            ),
            created_at=runtime.now_utc,
            applied_at=None,
            updated_at=runtime.now_utc,
        ),
    )


async def prepare_validated_redemption(
    runtime: PromoRedeemRuntime,
    *,
    promo_code: str,
    deps: PromoRedeemDeps,
) -> ValidatedPromoRedemption:
    code_lookup = build_promo_code_lookup(promo_code=promo_code, deps=deps)
    await _enforce_redeem_rate_limit(runtime, code_lookup=code_lookup, deps=deps)
    matched_code = await _resolve_matched_promo_code(runtime, code_lookup=code_lookup)
    await _validate_matched_promo_code(
        runtime,
        matched_code=matched_code,
        code_lookup=code_lookup,
        deps=deps,
    )
    return ValidatedPromoRedemption(
        matched_code=matched_code,
        code_hash=code_lookup.code_hash,
        redemption=await _create_validated_redemption(runtime, matched_code=matched_code),
    )
