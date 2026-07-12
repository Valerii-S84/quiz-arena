from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.production_reliability import TelegramDeliveryAttempt
from app.db.repo.production_reliability_types import DELIVERY_STATUS_FAILED, DELIVERY_STATUS_PENDING


class TelegramDeliveryRetryRepo:
    @staticmethod
    async def claim_retryable_attempt(
        session: AsyncSession,
        *,
        idempotency_key: str,
        claimed_at: datetime,
        retryable_failure_codes: frozenset[str],
        stale_pending_before: datetime,
        max_attempts: int,
        allow_stale_pending_retry: bool,
    ) -> int:
        retryable_failed = and_(
            TelegramDeliveryAttempt.status == DELIVERY_STATUS_FAILED,
            TelegramDeliveryAttempt.failure_code.in_(tuple(retryable_failure_codes)),
            TelegramDeliveryAttempt.is_blocked_candidate.is_(False),
            TelegramDeliveryAttempt.updated_at <= stale_pending_before,
        )
        stale_pending = and_(
            TelegramDeliveryAttempt.status == DELIVERY_STATUS_PENDING,
            TelegramDeliveryAttempt.updated_at <= stale_pending_before,
        )
        retry_conditions = [retryable_failed]
        if allow_stale_pending_retry:
            retry_conditions.append(stale_pending)
        stmt = (
            update(TelegramDeliveryAttempt)
            .where(
                TelegramDeliveryAttempt.idempotency_key == idempotency_key,
                TelegramDeliveryAttempt.attempt_count < max_attempts,
                or_(*retry_conditions),
            )
            .values(is_blocked_candidate=False, updated_at=claimed_at)
        )
        result = await session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    @staticmethod
    async def mark_retry_dispatched(
        session: AsyncSession,
        *,
        idempotency_key: str,
        claimed_at: datetime,
        retryable_failure_codes: frozenset[str],
        max_attempts: int,
    ) -> int:
        stmt = (
            update(TelegramDeliveryAttempt)
            .where(
                TelegramDeliveryAttempt.idempotency_key == idempotency_key,
                TelegramDeliveryAttempt.status == DELIVERY_STATUS_FAILED,
                TelegramDeliveryAttempt.failure_code.in_(tuple(retryable_failure_codes)),
                TelegramDeliveryAttempt.is_blocked_candidate.is_(False),
                TelegramDeliveryAttempt.attempt_count < max_attempts,
                TelegramDeliveryAttempt.updated_at == claimed_at,
            )
            .values(
                status=DELIVERY_STATUS_PENDING,
                failed_at=None,
                skipped_at=None,
                failure_code=None,
                failure_reason=None,
                telegram_error_code=None,
            )
        )
        result = await session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)


__all__ = ["TelegramDeliveryRetryRepo"]
