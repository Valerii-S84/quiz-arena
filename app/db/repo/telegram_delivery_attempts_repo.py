from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.production_reliability import TelegramDeliveryAttempt
from app.db.repo.production_reliability_types import (
    TelegramDeliveryAttemptCreate,
    TelegramDeliveryFailure,
)
from app.db.repo.telegram_delivery_retry_repo import TelegramDeliveryRetryRepo


class TelegramDeliveryAttemptsRepo(TelegramDeliveryRetryRepo):
    @staticmethod
    async def create_once(
        session: AsyncSession,
        *,
        attempt: TelegramDeliveryAttemptCreate,
    ) -> tuple[TelegramDeliveryAttempt, bool]:
        stmt = (
            postgresql_insert(TelegramDeliveryAttempt)
            .values(
                flow=attempt.flow,
                task_name=attempt.task_name,
                correlation_id=attempt.correlation_id,
                idempotency_key=attempt.idempotency_key,
                telegram_user_id=attempt.telegram_user_id,
                chat_id_hash=attempt.chat_id_hash,
                target_type=attempt.target_type,
                target_id=attempt.target_id,
                safe_context=attempt.safe_context,
                attempt_count=1,
                updated_at=func.now(),
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
            idempotency_key=attempt.idempotency_key,
        )
        if existing is None:
            raise RuntimeError("telegram_delivery_attempts idempotent insert returned no row")
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
        expected_attempt_count: int | None = None,
    ) -> bool:
        conditions = [
            TelegramDeliveryAttempt.idempotency_key == idempotency_key,
            TelegramDeliveryAttempt.status == "PENDING",
        ]
        if expected_attempt_count is not None:
            conditions.append(TelegramDeliveryAttempt.attempt_count == expected_attempt_count)
        stmt = (
            update(TelegramDeliveryAttempt)
            .where(*conditions)
            .values(
                status="SENT",
                sent_at=func.now(),
                failed_at=None,
                skipped_at=None,
                failure_code=None,
                failure_reason=None,
                telegram_error_code=None,
                is_blocked_candidate=False,
                updated_at=func.now(),
            )
            .returning(TelegramDeliveryAttempt.id)
        )
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            return True
        if expected_attempt_count is not None:
            return False

        replay_stmt = select(TelegramDeliveryAttempt.id).where(
            TelegramDeliveryAttempt.idempotency_key == idempotency_key,
            TelegramDeliveryAttempt.status == "SENT",
        )
        replay_result = await session.execute(replay_stmt)
        return replay_result.scalar_one_or_none() is not None

    @staticmethod
    async def mark_failed(
        session: AsyncSession,
        *,
        idempotency_key: str,
        failure: TelegramDeliveryFailure,
        expected_attempt_count: int | None = None,
    ) -> bool:
        conditions = [
            TelegramDeliveryAttempt.idempotency_key == idempotency_key,
            TelegramDeliveryAttempt.status == "PENDING",
        ]
        if expected_attempt_count is not None:
            conditions.append(TelegramDeliveryAttempt.attempt_count == expected_attempt_count)
        stmt = (
            update(TelegramDeliveryAttempt)
            .where(*conditions)
            .values(
                status="FAILED",
                failed_at=func.now(),
                skipped_at=None,
                failure_code=failure.failure_code,
                failure_reason=failure.failure_reason,
                telegram_error_code=failure.telegram_error_code,
                is_blocked_candidate=failure.is_blocked_candidate,
                updated_at=func.now(),
            )
            .returning(TelegramDeliveryAttempt.id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def mark_skipped(
        session: AsyncSession,
        *,
        idempotency_key: str,
        failure_code: str,
        failure_reason: str | None = None,
        expected_attempt_count: int | None = None,
    ) -> bool:
        conditions = [
            TelegramDeliveryAttempt.idempotency_key == idempotency_key,
            TelegramDeliveryAttempt.status == "PENDING",
        ]
        if expected_attempt_count is not None:
            conditions.append(TelegramDeliveryAttempt.attempt_count == expected_attempt_count)
        stmt = (
            update(TelegramDeliveryAttempt)
            .where(*conditions)
            .values(
                status="SKIPPED",
                skipped_at=func.now(),
                failed_at=None,
                failure_code=failure_code,
                failure_reason=failure_reason,
                telegram_error_code=None,
                is_blocked_candidate=False,
                updated_at=func.now(),
            )
            .returning(TelegramDeliveryAttempt.id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None
