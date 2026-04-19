from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.repo.promo_repo import PromoRepo
from app.db.repo.users_repo import UsersRepo
from app.economy.promo.attempts import record_attempt, record_failed_attempt
from app.economy.promo.grants import apply_premium_grant
from app.economy.promo.idempotency import build_idempotent_result
from app.economy.promo.rate_limit import enforce_rate_limit
from app.economy.promo.redeem_effects import apply_premium_grant_redemption
from app.economy.promo.redeem_validation import (
    ensure_code_is_current,
    ensure_purchase_eligibility,
    ensure_retry_allowed,
)
from app.economy.promo.service_redeem import redeem_promo_code
from app.economy.promo.service_redeem_context import PromoRedeemDeps
from app.economy.promo.types import PromoRedeemResult
from app.services.promo_codes import hash_promo_code, normalize_promo_code

__all__ = ["PromoRepo", "UsersRepo", "PromoService"]


def _build_promo_redeem_deps() -> PromoRedeemDeps:
    return PromoRedeemDeps(
        record_attempt=PromoService._record_attempt,
        record_failed_attempt=PromoService._record_failed_attempt,
        enforce_rate_limit=PromoService._enforce_rate_limit,
        build_idempotent_result=PromoService._build_idempotent_result,
        apply_premium_grant=PromoService._apply_premium_grant,
        normalize_promo_code=normalize_promo_code,
        hash_promo_code=hash_promo_code,
        get_settings=get_settings,
        ensure_retry_allowed=ensure_retry_allowed,
        ensure_code_is_current=ensure_code_is_current,
        ensure_purchase_eligibility=ensure_purchase_eligibility,
        apply_premium_grant_redemption=apply_premium_grant_redemption,
    )


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
        return await redeem_promo_code(
            session,
            user_id=user_id,
            promo_code=promo_code,
            idempotency_key=idempotency_key,
            source=source,
            now_utc=now_utc,
            deps=_build_promo_redeem_deps(),
        )
