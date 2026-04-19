from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promo_redemptions import PromoRedemption


@dataclass(slots=True)
class PromoAttemptWriters:
    record_attempt: Any
    record_failed_attempt: Any


@dataclass(slots=True)
class PromoRedeemRuntime:
    session: AsyncSession
    user_id: int
    idempotency_key: str
    now_utc: datetime
    attempts: PromoAttemptWriters


@dataclass(slots=True)
class PromoCodeLookup:
    normalized_code: str
    code_hash: str


@dataclass(slots=True)
class ValidatedPromoRedemption:
    matched_code: Any
    code_hash: str
    redemption: PromoRedemption


@dataclass(slots=True)
class PromoRedeemDeps:
    record_attempt: Any
    record_failed_attempt: Any
    enforce_rate_limit: Any
    build_idempotent_result: Any
    apply_premium_grant: Any
    normalize_promo_code: Any
    hash_promo_code: Any
    get_settings: Any
    ensure_retry_allowed: Any
    ensure_code_is_current: Any
    ensure_purchase_eligibility: Any
    apply_premium_grant_redemption: Any


def _build_promo_attempt_writers(
    *,
    source: str,
    deps: PromoRedeemDeps,
) -> PromoAttemptWriters:
    return PromoAttemptWriters(
        record_attempt=partial(deps.record_attempt, source=source),
        record_failed_attempt=partial(deps.record_failed_attempt, source=source),
    )


def build_promo_redeem_runtime(
    session: AsyncSession,
    *,
    user_id: int,
    idempotency_key: str,
    source: str,
    now_utc: datetime | None,
    deps: PromoRedeemDeps,
) -> PromoRedeemRuntime:
    return PromoRedeemRuntime(
        session=session,
        user_id=user_id,
        idempotency_key=idempotency_key,
        now_utc=now_utc or datetime.now(timezone.utc),
        attempts=_build_promo_attempt_writers(source=source, deps=deps),
    )


def build_promo_code_lookup(
    *,
    promo_code: str,
    deps: PromoRedeemDeps,
) -> PromoCodeLookup:
    normalized_code = deps.normalize_promo_code(promo_code)
    return PromoCodeLookup(
        normalized_code=normalized_code,
        code_hash=deps.hash_promo_code(
            normalized_code=normalized_code,
            pepper=deps.get_settings().promo_secret_pepper,
        ),
    )
