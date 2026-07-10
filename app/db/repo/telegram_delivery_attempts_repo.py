from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.production_reliability import TelegramDeliveryAttempt
from app.db.repo.production_reliability_types import (
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_PENDING,
    DELIVERY_STATUS_SENT,
    DELIVERY_STATUS_SKIPPED,
    DeliveryAttemptCreate,
)
from app.db.repo.telegram_blocked_candidates_repo import TelegramBlockedCandidatesRepo


class TelegramDeliveryAttemptsRepo(TelegramBlockedCandidatesRepo):
    @staticmethod
    async def create_pending_once(
        session: AsyncSession,
        *,
        item: DeliveryAttemptCreate,
    ) -> tuple[TelegramDeliveryAttempt, bool]:
        stmt = (
            insert(TelegramDeliveryAttempt)
            .values(
                flow=item.flow,
                task_name=item.task_name,
                correlation_id=item.correlation_id,
                idempotency_key=item.idempotency_key,
                telegram_user_id=item.telegram_user_id,
                chat_id_hash=item.chat_id_hash,
                target_type=item.target_type,
                target_id=item.target_id,
                status=DELIVERY_STATUS_PENDING,
                safe_context=item.safe_context or {},
            )
            .on_conflict_do_nothing(index_elements=[TelegramDeliveryAttempt.idempotency_key])
            .returning(TelegramDeliveryAttempt)
        )
        result = await session.execute(stmt)
        created = result.scalar_one_or_none()
        if created is not None:
            return created, True
        existing = await TelegramDeliveryAttemptsRepo.get_by_idempotency_key(
            session,
            idempotency_key=item.idempotency_key,
        )
        if existing is None:
            raise RuntimeError("telegram_delivery_attempt idempotent insert returned no row")
        return existing, False

    @staticmethod
    async def get_by_idempotency_key(
        session: AsyncSession,
        *,
        idempotency_key: str,
    ) -> TelegramDeliveryAttempt | None:
        stmt = select(TelegramDeliveryAttempt).where(
            TelegramDeliveryAttempt.idempotency_key == idempotency_key
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_sent(
        session: AsyncSession,
        *,
        idempotency_key: str,
        sent_at: datetime,
    ) -> int:
        stmt = (
            update(TelegramDeliveryAttempt)
            .where(
                TelegramDeliveryAttempt.idempotency_key == idempotency_key,
                TelegramDeliveryAttempt.status == DELIVERY_STATUS_PENDING,
            )
            .values(
                status=DELIVERY_STATUS_SENT,
                attempt_count=TelegramDeliveryAttempt.attempt_count + 1,
                sent_at=sent_at,
                failed_at=None,
                skipped_at=None,
                failure_code=None,
                failure_reason=None,
                telegram_error_code=None,
                updated_at=sent_at,
            )
        )
        result = await session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    @staticmethod
    async def mark_failed(
        session: AsyncSession,
        *,
        idempotency_key: str,
        failed_at: datetime,
        failure_code: str,
        failure_reason: str,
        telegram_error_code: int | None,
        is_blocked_candidate: bool,
    ) -> int:
        stmt = (
            update(TelegramDeliveryAttempt)
            .where(
                TelegramDeliveryAttempt.idempotency_key == idempotency_key,
                TelegramDeliveryAttempt.status == DELIVERY_STATUS_PENDING,
            )
            .values(
                status=DELIVERY_STATUS_FAILED,
                attempt_count=TelegramDeliveryAttempt.attempt_count + 1,
                failed_at=failed_at,
                skipped_at=None,
                failure_code=failure_code,
                failure_reason=failure_reason,
                telegram_error_code=telegram_error_code,
                is_blocked_candidate=is_blocked_candidate,
                updated_at=failed_at,
            )
        )
        result = await session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    @staticmethod
    async def mark_skipped(
        session: AsyncSession,
        *,
        idempotency_key: str,
        skipped_at: datetime,
        failure_code: str,
        failure_reason: str,
    ) -> int:
        stmt = (
            update(TelegramDeliveryAttempt)
            .where(
                TelegramDeliveryAttempt.idempotency_key == idempotency_key,
                TelegramDeliveryAttempt.status == DELIVERY_STATUS_PENDING,
            )
            .values(
                status=DELIVERY_STATUS_SKIPPED,
                skipped_at=skipped_at,
                failed_at=None,
                failure_code=failure_code,
                failure_reason=failure_reason,
                updated_at=skipped_at,
            )
        )
        result = await session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

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
            .values(
                status=DELIVERY_STATUS_PENDING,
                failed_at=None,
                skipped_at=None,
                failure_code=None,
                failure_reason=None,
                telegram_error_code=None,
                is_blocked_candidate=False,
                updated_at=claimed_at,
            )
        )
        result = await session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    @staticmethod
    async def count_outcomes(
        session: AsyncSession,
        *,
        flow: str,
        correlation_id: str,
    ) -> dict[str, int]:
        stmt = (
            select(TelegramDeliveryAttempt.status, func.count(TelegramDeliveryAttempt.id))
            .where(
                TelegramDeliveryAttempt.flow == flow,
                TelegramDeliveryAttempt.correlation_id == correlation_id,
            )
            .group_by(TelegramDeliveryAttempt.status)
        )
        result = await session.execute(stmt)
        return {str(status): int(total) for status, total in result.all()}
