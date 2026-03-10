from __future__ import annotations

from datetime import datetime, timezone
from functools import partial
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
        now_utc = now_utc or datetime.now(timezone.utc)
        record_attempt = partial(PromoService._record_attempt, source=source)
        record_failed_attempt = partial(PromoService._record_failed_attempt, source=source)

        existing = await PromoRepo.get_redemption_by_idempotency_key_for_update(
            session, idempotency_key
        )
        if existing is not None:
            if existing.user_id != user_id:
                raise PromoIdempotencyConflictError
            return await PromoService._build_idempotent_result(session, redemption=existing)

        user = await UsersRepo.get_by_id(session, user_id)
        if user is None:
            raise PromoUserNotFoundError

        normalized_code = normalize_promo_code(promo_code)
        code_hash = hash_promo_code(
            normalized_code=normalized_code,
            pepper=get_settings().promo_secret_pepper,
        )

        try:
            await PromoService._enforce_rate_limit(session, user_id=user_id, now_utc=now_utc)
        except PromoRateLimitedError:
            await record_failed_attempt(
                user_id=user_id,
                normalized_code_hash=code_hash,
                result="RATE_LIMITED",
                now_utc=now_utc,
                metadata={"idempotency_key": idempotency_key},
            )
            raise

        if not normalized_code:
            await record_failed_attempt(
                user_id=user_id,
                normalized_code_hash=code_hash,
                result="INVALID",
                now_utc=now_utc,
                metadata={"reason": "EMPTY"},
            )
            raise PromoInvalidError

        matched_code = await PromoRepo.get_code_by_hash_for_update(session, code_hash)
        if matched_code is None:
            await record_failed_attempt(
                user_id=user_id,
                normalized_code_hash=code_hash,
                result="INVALID",
                now_utc=now_utc,
            )
            raise PromoInvalidError

        previous_redemptions = await PromoRepo.list_redemptions_by_code_and_user_for_update(
            session,
            promo_code_id=matched_code.id,
            user_id=user_id,
        )
        await ensure_retry_allowed(
            redemptions=previous_redemptions,
            promo_code=matched_code,
            user_id=user_id,
            code_hash=code_hash,
            now_utc=now_utc,
            record_failed_attempt=record_failed_attempt,
        )
        await ensure_code_is_current(
            promo_code=matched_code,
            user_id=user_id,
            code_hash=code_hash,
            now_utc=now_utc,
            record_failed_attempt=record_failed_attempt,
        )
        await ensure_purchase_eligibility(
            session,
            promo_code=matched_code,
            user_id=user_id,
            code_hash=code_hash,
            now_utc=now_utc,
            record_failed_attempt=record_failed_attempt,
        )

        redemption = await PromoRepo.create_redemption(
            session,
            redemption=PromoRedemption(
                id=uuid4(),
                promo_code_id=matched_code.id,
                user_id=user_id,
                status="VALIDATED",
                reject_reason=None,
                reserved_until=None,
                applied_purchase_id=None,
                grant_entitlement_id=None,
                idempotency_key=idempotency_key,
                validation_snapshot=build_validation_snapshot(
                    promo_code=matched_code,
                    now_utc=now_utc,
                ),
                created_at=now_utc,
                applied_at=None,
                updated_at=now_utc,
            ),
        )

        if matched_code.promo_type == "PREMIUM_GRANT":
            result = await apply_premium_grant_redemption(
                session,
                user_id=user_id,
                redemption=redemption,
                now_utc=now_utc,
                promo_code=matched_code,
                apply_premium_grant=PromoService._apply_premium_grant,
            )
            await record_attempt(
                session,
                user_id=user_id,
                normalized_code_hash=code_hash,
                result="ACCEPTED",
                now_utc=now_utc,
                metadata={"redemption_id": str(redemption.id)},
            )
            return result

        if matched_code.promo_type == "PERCENT_DISCOUNT":
            if matched_code.discount_type is None and matched_code.discount_percent is None:
                raise PromoNotApplicableError

            await record_attempt(
                session,
                user_id=user_id,
                normalized_code_hash=code_hash,
                result="ACCEPTED",
                now_utc=now_utc,
                metadata={"redemption_id": str(redemption.id)},
            )
            return reserve_discount_redemption(
                redemption=redemption,
                promo_code=matched_code,
                now_utc=now_utc,
            )

        raise PromoInvalidError
