from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.entitlements import Entitlement
from app.db.models.ledger_entries import LedgerEntry
from app.db.models.promo_attempts import PromoAttempt
from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.ledger_repo import LedgerRepo
from app.db.repo.promo_repo import PromoRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.promo.errors import (
    PromoAlreadyUsedError,
    PromoExpiredError,
    PromoIdempotencyConflictError,
    PromoInvalidError,
    PromoNotApplicableError,
    PromoRateLimitedError,
    PromoUserNotFoundError,
)
from app.economy.promo.types import PromoRedeemResult
from app.services.promo_codes import hash_promo_code, normalize_promo_code

FAILED_PROMO_ATTEMPT_RESULTS = ("INVALID", "EXPIRED", "NOT_APPLICABLE")
PROMO_ATTEMPT_BLOCK_WINDOW = timedelta(hours=1)
PROMO_ATTEMPT_RATE_LIMIT_WINDOW = timedelta(hours=24)
PROMO_ATTEMPT_MAX_FAILURES = 5
PROMO_DISCOUNT_RESERVATION_TTL = timedelta(days=7)
PROMO_PREMIUM_SCOPE_BY_DAYS: dict[int, str] = {
    7: "PREMIUM_STARTER",
    30: "PREMIUM_MONTH",
    90: "PREMIUM_SEASON",
}


class PromoService:
    @staticmethod
    async def _record_attempt(
        session: AsyncSession,
        *,
        user_id: int,
        normalized_code_hash: str,
        result: str,
        now_utc: datetime,
        metadata: dict[str, object] | None = None,
    ) -> None:
        await PromoRepo.create_attempt(
            session,
            attempt=PromoAttempt(
                user_id=user_id,
                normalized_code_hash=normalized_code_hash,
                result=result,
                source="API",
                attempted_at=now_utc,
                metadata_=metadata or {},
            ),
        )

    @staticmethod
    async def _record_failed_attempt(
        *,
        user_id: int,
        normalized_code_hash: str,
        result: str,
        now_utc: datetime,
        metadata: dict[str, object] | None = None,
    ) -> None:
        async with SessionLocal.begin() as attempt_session:
            await PromoService._record_attempt(
                attempt_session,
                user_id=user_id,
                normalized_code_hash=normalized_code_hash,
                result=result,
                now_utc=now_utc,
                metadata=metadata,
            )

    @staticmethod
    async def _enforce_rate_limit(
        session: AsyncSession,
        *,
        user_id: int,
        now_utc: datetime,
    ) -> None:
        block_since = now_utc - PROMO_ATTEMPT_BLOCK_WINDOW
        recently_rate_limited = await PromoRepo.count_user_attempts(
            session,
            user_id=user_id,
            since_utc=block_since,
            attempt_results=("RATE_LIMITED",),
        )
        if recently_rate_limited > 0:
            raise PromoRateLimitedError

        window_start = now_utc - PROMO_ATTEMPT_RATE_LIMIT_WINDOW
        failed_attempts = await PromoRepo.count_user_attempts(
            session,
            user_id=user_id,
            since_utc=window_start,
            attempt_results=FAILED_PROMO_ATTEMPT_RESULTS,
        )
        if failed_attempts < PROMO_ATTEMPT_MAX_FAILURES:
            return

        last_failed_at = await PromoRepo.get_last_user_attempt_at(
            session,
            user_id=user_id,
            since_utc=window_start,
            attempt_results=FAILED_PROMO_ATTEMPT_RESULTS,
        )
        if last_failed_at is not None and last_failed_at > block_since:
            raise PromoRateLimitedError

    @staticmethod
    async def _build_idempotent_result(
        session: AsyncSession,
        *,
        redemption: PromoRedemption,
    ) -> PromoRedeemResult:
        promo_code = await PromoRepo.get_code_by_id(session, redemption.promo_code_id)
        if promo_code is None:
            raise PromoInvalidError

        if promo_code.promo_type == "PREMIUM_GRANT":
            entitlement = None
            if redemption.grant_entitlement_id is not None:
                entitlement = await session.get(Entitlement, redemption.grant_entitlement_id)
            return PromoRedeemResult(
                redemption_id=redemption.id,
                result_type="PREMIUM_GRANT",
                idempotent_replay=True,
                premium_days=promo_code.grant_premium_days,
                premium_ends_at=(entitlement.ends_at if entitlement is not None else None),
            )

        if promo_code.promo_type == "PERCENT_DISCOUNT":
            return PromoRedeemResult(
                redemption_id=redemption.id,
                result_type="PERCENT_DISCOUNT",
                idempotent_replay=True,
                discount_percent=promo_code.discount_percent,
                reserved_until=redemption.reserved_until,
                target_scope=promo_code.target_scope,
            )

        raise PromoInvalidError

    @staticmethod
    async def _apply_premium_grant(
        session: AsyncSession,
        *,
        user_id: int,
        redemption: PromoRedemption,
        promo_code: PromoCode,
        now_utc: datetime,
    ) -> Entitlement:
        if promo_code.grant_premium_days is None or promo_code.grant_premium_days <= 0:
            raise PromoNotApplicableError

        grant_days = promo_code.grant_premium_days
        active_entitlement = await EntitlementsRepo.get_active_premium_for_update(
            session, user_id, now_utc
        )
        if active_entitlement is not None:
            base_end = (
                active_entitlement.ends_at
                if active_entitlement.ends_at and active_entitlement.ends_at > now_utc
                else now_utc
            )
            active_entitlement.ends_at = base_end + timedelta(days=grant_days)
            active_entitlement.updated_at = now_utc
            entitlement = active_entitlement
        else:
            entitlement = await EntitlementsRepo.create(
                session,
                entitlement=Entitlement(
                    user_id=user_id,
                    entitlement_type="PREMIUM",
                    scope=PROMO_PREMIUM_SCOPE_BY_DAYS.get(grant_days, "PREMIUM_MONTH"),
                    status="ACTIVE",
                    starts_at=now_utc,
                    ends_at=now_utc + timedelta(days=grant_days),
                    source_purchase_id=None,
                    idempotency_key=f"entitlement:promo:{redemption.id}",
                    metadata_={
                        "promo_redemption_id": str(redemption.id),
                        "promo_code_id": promo_code.id,
                    },
                    created_at=now_utc,
                    updated_at=now_utc,
                ),
            )

        await LedgerRepo.create(
            session,
            entry=LedgerEntry(
                user_id=user_id,
                purchase_id=None,
                entry_type="PROMO_GRANT",
                asset="PREMIUM",
                direction="CREDIT",
                amount=grant_days,
                balance_after=None,
                source="PROMO",
                idempotency_key=f"promo:grant:{redemption.id}",
                metadata_={
                    "promo_redemption_id": str(redemption.id),
                    "promo_code_id": promo_code.id,
                    "grant_days": grant_days,
                },
                created_at=now_utc,
            ),
        )
        return entitlement

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
