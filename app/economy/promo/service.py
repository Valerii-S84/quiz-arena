from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.promo_repo import PromoRepo
from app.db.repo.users_repo import UsersRepo
from app.economy.promo.attempts import record_attempt, record_failed_attempt
from app.economy.promo.errors import (
    PromoIdempotencyConflictError,
    PromoInvalidError,
    PromoNotApplicableError,
    PromoRateLimitedError,
    PromoUserNotFoundError,
)
from app.economy.promo.grants import apply_premium_grant
from app.economy.promo.idempotency import build_idempotent_result
from app.economy.promo.rate_limit import enforce_rate_limit
from app.economy.promo.redeem_effects import (
    apply_premium_grant_redemption,
    build_validation_snapshot,
    reserve_discount_redemption,
)
from app.economy.promo.redeem_validation import (
    ensure_code_is_current,
    ensure_purchase_eligibility,
    ensure_retry_allowed,
)
from app.economy.promo.types import PromoRedeemResult
from app.services.promo_codes import hash_promo_code, normalize_promo_code


@dataclass(slots=True)
class _PromoAttemptWriters:
    record_attempt: Any
    record_failed_attempt: Any


@dataclass(slots=True)
class _PromoRedeemRuntime:
    session: AsyncSession
    user_id: int
    idempotency_key: str
    now_utc: datetime
    attempts: _PromoAttemptWriters


@dataclass(slots=True)
class _PromoCodeLookup:
    normalized_code: str
    code_hash: str


@dataclass(slots=True)
class _ValidatedPromoRedemption:
    matched_code: Any
    code_hash: str
    redemption: PromoRedemption


def _build_promo_attempt_writers(*, source: str) -> _PromoAttemptWriters:
    return _PromoAttemptWriters(
        record_attempt=partial(PromoService._record_attempt, source=source),
        record_failed_attempt=partial(PromoService._record_failed_attempt, source=source),
    )


def _build_promo_redeem_runtime(
    session: AsyncSession,
    *,
    user_id: int,
    idempotency_key: str,
    source: str,
    now_utc: datetime | None,
) -> _PromoRedeemRuntime:
    return _PromoRedeemRuntime(
        session=session,
        user_id=user_id,
        idempotency_key=idempotency_key,
        now_utc=now_utc or datetime.now(timezone.utc),
        attempts=_build_promo_attempt_writers(source=source),
    )


async def _resolve_idempotent_redeem_result(
    runtime: _PromoRedeemRuntime,
) -> PromoRedeemResult | None:
    existing = await PromoRepo.get_redemption_by_idempotency_key_for_update(
        runtime.session,
        runtime.idempotency_key,
    )
    if existing is None:
        return None
    if existing.user_id != runtime.user_id:
        raise PromoIdempotencyConflictError
    return await PromoService._build_idempotent_result(runtime.session, redemption=existing)


async def _ensure_redeem_user_exists(runtime: _PromoRedeemRuntime) -> None:
    user = await UsersRepo.get_by_id(runtime.session, runtime.user_id)
    if user is None:
        raise PromoUserNotFoundError


def _build_promo_code_lookup(*, promo_code: str) -> _PromoCodeLookup:
    normalized_code = normalize_promo_code(promo_code)
    return _PromoCodeLookup(
        normalized_code=normalized_code,
        code_hash=hash_promo_code(
            normalized_code=normalized_code,
            pepper=get_settings().promo_secret_pepper,
        ),
    )


async def _record_invalid_code_and_raise(
    runtime: _PromoRedeemRuntime,
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
    runtime: _PromoRedeemRuntime,
    *,
    code_lookup: _PromoCodeLookup,
) -> None:
    try:
        await PromoService._enforce_rate_limit(
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
    runtime: _PromoRedeemRuntime,
    *,
    code_lookup: _PromoCodeLookup,
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
    runtime: _PromoRedeemRuntime,
    *,
    matched_code,
    code_lookup: _PromoCodeLookup,
) -> None:
    previous_redemptions = await PromoRepo.list_redemptions_by_code_and_user_for_update(
        runtime.session,
        promo_code_id=matched_code.id,
        user_id=runtime.user_id,
    )
    await ensure_retry_allowed(
        redemptions=previous_redemptions,
        promo_code=matched_code,
        user_id=runtime.user_id,
        code_hash=code_lookup.code_hash,
        now_utc=runtime.now_utc,
        record_failed_attempt=runtime.attempts.record_failed_attempt,
    )
    await ensure_code_is_current(
        promo_code=matched_code,
        user_id=runtime.user_id,
        code_hash=code_lookup.code_hash,
        now_utc=runtime.now_utc,
        record_failed_attempt=runtime.attempts.record_failed_attempt,
    )
    await ensure_purchase_eligibility(
        runtime.session,
        promo_code=matched_code,
        user_id=runtime.user_id,
        code_hash=code_lookup.code_hash,
        now_utc=runtime.now_utc,
        record_failed_attempt=runtime.attempts.record_failed_attempt,
    )


async def _create_validated_redemption(
    runtime: _PromoRedeemRuntime,
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


async def _prepare_validated_redemption(
    runtime: _PromoRedeemRuntime,
    *,
    promo_code: str,
) -> _ValidatedPromoRedemption:
    code_lookup = _build_promo_code_lookup(promo_code=promo_code)
    await _enforce_redeem_rate_limit(runtime, code_lookup=code_lookup)
    matched_code = await _resolve_matched_promo_code(runtime, code_lookup=code_lookup)
    await _validate_matched_promo_code(
        runtime,
        matched_code=matched_code,
        code_lookup=code_lookup,
    )
    return _ValidatedPromoRedemption(
        matched_code=matched_code,
        code_hash=code_lookup.code_hash,
        redemption=await _create_validated_redemption(runtime, matched_code=matched_code),
    )


async def _record_accepted_attempt(
    runtime: _PromoRedeemRuntime,
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
    runtime: _PromoRedeemRuntime,
    *,
    validated_redemption: _ValidatedPromoRedemption,
) -> PromoRedeemResult:
    result = await apply_premium_grant_redemption(
        runtime.session,
        user_id=runtime.user_id,
        redemption=validated_redemption.redemption,
        now_utc=runtime.now_utc,
        promo_code=validated_redemption.matched_code,
        apply_premium_grant=PromoService._apply_premium_grant,
    )
    await _record_accepted_attempt(
        runtime,
        code_hash=validated_redemption.code_hash,
        redemption=validated_redemption.redemption,
    )
    return result


async def _apply_discount_result(
    runtime: _PromoRedeemRuntime,
    *,
    validated_redemption: _ValidatedPromoRedemption,
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
    runtime: _PromoRedeemRuntime,
    *,
    validated_redemption: _ValidatedPromoRedemption,
) -> PromoRedeemResult:
    if validated_redemption.matched_code.promo_type == "PREMIUM_GRANT":
        return await _apply_premium_grant_result(
            runtime,
            validated_redemption=validated_redemption,
        )
    if validated_redemption.matched_code.promo_type == "PERCENT_DISCOUNT":
        return await _apply_discount_result(
            runtime,
            validated_redemption=validated_redemption,
        )
    raise PromoInvalidError


class PromoService:
    _record_attempt = staticmethod(record_attempt)
    _record_failed_attempt = staticmethod(record_failed_attempt)
    _enforce_rate_limit = staticmethod(enforce_rate_limit)
    _build_idempotent_result = staticmethod(build_idempotent_result)
    _apply_premium_grant = staticmethod(apply_premium_grant)

    @staticmethod
    async def redeem(
        session: AsyncSession,
        *,
        user_id: int,
        promo_code: str,
        idempotency_key: str,
        source: str = "API",
        now_utc: datetime | None = None,
    ) -> PromoRedeemResult:
        runtime = _build_promo_redeem_runtime(
            session,
            user_id=user_id,
            idempotency_key=idempotency_key,
            source=source,
            now_utc=now_utc,
        )
        idempotent_result = await _resolve_idempotent_redeem_result(runtime)
        if idempotent_result is not None:
            return idempotent_result

        await _ensure_redeem_user_exists(runtime)
        validated_redemption = await _prepare_validated_redemption(
            runtime,
            promo_code=promo_code,
        )
        return await _apply_redeem_result(
            runtime,
            validated_redemption=validated_redemption,
        )
