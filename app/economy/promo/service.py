from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.promo_repo import PromoRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.users_repo import UsersRepo
from app.economy.promo.attempts import record_attempt, record_failed_attempt
from app.economy.promo.constants import PROMO_DISCOUNT_RESERVATION_TTL
from app.economy.promo.errors import (
    PromoAlreadyUsedError,
    PromoExpiredError,
    PromoIdempotencyConflictError,
    PromoInvalidError,
    PromoNotApplicableError,
    PromoRateLimitedError,
    PromoUserNotFoundError,
)
from app.economy.promo.grants import apply_premium_grant
from app.economy.promo.idempotency import build_idempotent_result
from app.economy.promo.rate_limit import enforce_rate_limit
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
        now_utc: datetime | None = None,
    ) -> PromoRedeemResult:
        now_utc = now_utc or datetime.now(timezone.utc)

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
            await PromoService._record_failed_attempt(
                user_id=user_id,
                normalized_code_hash=code_hash,
                result="RATE_LIMITED",
                now_utc=now_utc,
                metadata={"idempotency_key": idempotency_key},
            )
            raise

        if not normalized_code:
            await PromoService._record_failed_attempt(
                user_id=user_id,
                normalized_code_hash=code_hash,
                result="INVALID",
                now_utc=now_utc,
                metadata={"reason": "EMPTY"},
            )
            raise PromoInvalidError

        matched_code = await PromoRepo.get_code_by_hash_for_update(session, code_hash)
        if matched_code is None:
            await PromoService._record_failed_attempt(
                user_id=user_id,
                normalized_code_hash=code_hash,
                result="INVALID",
                now_utc=now_utc,
            )
            raise PromoInvalidError

        existing_redemption = await PromoRepo.get_redemption_by_code_and_user_for_update(
            session,
            promo_code_id=matched_code.id,
            user_id=user_id,
        )
        if existing_redemption is not None:
            await PromoService._record_failed_attempt(
                user_id=user_id,
                normalized_code_hash=code_hash,
                result="NOT_APPLICABLE",
                now_utc=now_utc,
                metadata={
                    "reason": "ALREADY_USED",
                    "redemption_id": str(existing_redemption.id),
                },
            )
            raise PromoAlreadyUsedError

        if matched_code.status != "ACTIVE" or not (
            matched_code.valid_from <= now_utc < matched_code.valid_until
        ):
            await PromoService._record_failed_attempt(
                user_id=user_id,
                normalized_code_hash=code_hash,
                result="EXPIRED",
                now_utc=now_utc,
            )
            raise PromoExpiredError
        if (
            matched_code.max_total_uses is not None
            and matched_code.used_total >= matched_code.max_total_uses
        ):
            await PromoService._record_failed_attempt(
                user_id=user_id,
                normalized_code_hash=code_hash,
                result="EXPIRED",
                now_utc=now_utc,
                metadata={"reason": "DEPLETED"},
            )
            raise PromoExpiredError

        purchase_count = 0
        if matched_code.new_users_only or matched_code.first_purchase_only:
            purchase_count = await PurchasesRepo.count_by_user(session, user_id=user_id)

        if matched_code.new_users_only and purchase_count > 0:
            await PromoService._record_failed_attempt(
                user_id=user_id,
                normalized_code_hash=code_hash,
                result="NOT_APPLICABLE",
                now_utc=now_utc,
                metadata={"reason": "NEW_USERS_ONLY"},
            )
            raise PromoNotApplicableError
        if matched_code.first_purchase_only and purchase_count > 0:
            await PromoService._record_failed_attempt(
                user_id=user_id,
                normalized_code_hash=code_hash,
                result="NOT_APPLICABLE",
                now_utc=now_utc,
                metadata={"reason": "FIRST_PURCHASE_ONLY"},
            )
            raise PromoNotApplicableError

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
                validation_snapshot={
                    "promo_type": matched_code.promo_type,
                    "target_scope": matched_code.target_scope,
                    "validated_at": now_utc.isoformat(),
                },
                created_at=now_utc,
                applied_at=None,
                updated_at=now_utc,
            ),
        )

        if matched_code.promo_type == "PREMIUM_GRANT":
            entitlement = await PromoService._apply_premium_grant(
                session,
                user_id=user_id,
                redemption=redemption,
                promo_code=matched_code,
                now_utc=now_utc,
            )
            redemption.status = "APPLIED"
            redemption.applied_at = now_utc
            redemption.grant_entitlement_id = entitlement.id
            redemption.updated_at = now_utc
            matched_code.used_total += 1
            matched_code.updated_at = now_utc

            await PromoService._record_attempt(
                session,
                user_id=user_id,
                normalized_code_hash=code_hash,
                result="ACCEPTED",
                now_utc=now_utc,
                metadata={"redemption_id": str(redemption.id)},
            )
            return PromoRedeemResult(
                redemption_id=redemption.id,
                result_type="PREMIUM_GRANT",
                idempotent_replay=False,
                premium_days=matched_code.grant_premium_days,
                premium_ends_at=entitlement.ends_at,
            )

        if matched_code.promo_type == "PERCENT_DISCOUNT":
            if matched_code.discount_percent is None:
                raise PromoNotApplicableError

            reserved_until = now_utc + PROMO_DISCOUNT_RESERVATION_TTL
            redemption.status = "RESERVED"
            redemption.reserved_until = reserved_until
            redemption.updated_at = now_utc

            await PromoService._record_attempt(
                session,
                user_id=user_id,
                normalized_code_hash=code_hash,
                result="ACCEPTED",
                now_utc=now_utc,
                metadata={"redemption_id": str(redemption.id)},
            )
            return PromoRedeemResult(
                redemption_id=redemption.id,
                result_type="PERCENT_DISCOUNT",
                idempotent_replay=False,
                discount_percent=matched_code.discount_percent,
                reserved_until=reserved_until,
                target_scope=matched_code.target_scope,
            )

        raise PromoInvalidError
