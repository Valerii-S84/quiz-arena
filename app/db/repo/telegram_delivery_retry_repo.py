from __future__ import annotations

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.production_reliability import TelegramDeliveryAttempt

PENDING_REPLAY_SAFE_CONTEXT_KEY = "pending_replay_safe"
RETRY_NEEDED_FAILURE_CODE = "TELEGRAM_RETRY_NEEDED"


class TelegramDeliveryRetryRepo:
    supports_delivery_lease_cas = True

    @staticmethod
    async def claim_pending_batch(
        session: AsyncSession,
        *,
        flow: str,
        limit: int,
        claim_ttl_seconds: int = 300,
    ) -> list[TelegramDeliveryAttempt]:
        claim_age_seconds = func.extract("epoch", func.now() - TelegramDeliveryAttempt.updated_at)
        replay_is_safe = or_(
            TelegramDeliveryAttempt.safe_context[PENDING_REPLAY_SAFE_CONTEXT_KEY]
            .as_boolean()
            .is_(True),
            TelegramDeliveryAttempt.failure_code == RETRY_NEEDED_FAILURE_CODE,
        )
        candidate_ids = (
            select(TelegramDeliveryAttempt.id)
            .where(
                TelegramDeliveryAttempt.flow == flow,
                TelegramDeliveryAttempt.status == "PENDING",
                replay_is_safe,
                or_(
                    TelegramDeliveryAttempt.attempt_count == 0,
                    claim_age_seconds >= max(1, int(claim_ttl_seconds)),
                ),
            )
            .order_by(
                TelegramDeliveryAttempt.created_at.asc(),
                TelegramDeliveryAttempt.id.asc(),
            )
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )
        stmt = (
            update(TelegramDeliveryAttempt)
            .where(TelegramDeliveryAttempt.id.in_(candidate_ids))
            .values(
                attempt_count=TelegramDeliveryAttempt.attempt_count + 1,
                updated_at=func.now(),
            )
            .returning(TelegramDeliveryAttempt)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def defer_retry_after(
        session: AsyncSession,
        *,
        idempotency_key: str,
        retry_after_seconds: int,
        claim_ttl_seconds: int = 300,
        expected_attempt_count: int | None = None,
        retry_failure_code: str | None = None,
        retry_failure_reason: str | None = None,
    ) -> bool:
        retry_after = max(1, int(retry_after_seconds))
        claim_ttl = max(1, int(claim_ttl_seconds))
        retry_offset = claim_ttl - retry_after
        conditions = [
            TelegramDeliveryAttempt.idempotency_key == idempotency_key,
            TelegramDeliveryAttempt.status == "PENDING",
        ]
        if expected_attempt_count is not None:
            conditions.append(TelegramDeliveryAttempt.attempt_count == expected_attempt_count)
        values: dict[str, object] = {
            "attempt_count": TelegramDeliveryAttempt.attempt_count + 1,
            "updated_at": func.now() - func.make_interval(0, 0, 0, 0, 0, 0, retry_offset),
        }
        if retry_failure_code is not None:
            values["failure_code"] = retry_failure_code
            values["failure_reason"] = retry_failure_reason
        stmt = (
            update(TelegramDeliveryAttempt)
            .where(*conditions)
            .values(**values)
            .returning(TelegramDeliveryAttempt.id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def claim_stale_pending_replay(
        session: AsyncSession,
        *,
        idempotency_key: str,
        claim_ttl_seconds: int = 300,
    ) -> int | None:
        claim_ttl = max(1, int(claim_ttl_seconds))
        stmt = (
            update(TelegramDeliveryAttempt)
            .where(
                TelegramDeliveryAttempt.idempotency_key == idempotency_key,
                TelegramDeliveryAttempt.status == "PENDING",
                TelegramDeliveryAttempt.updated_at
                <= func.now() - func.make_interval(0, 0, 0, 0, 0, 0, claim_ttl),
            )
            .values(
                attempt_count=TelegramDeliveryAttempt.attempt_count + 1,
                updated_at=func.now(),
            )
            .returning(TelegramDeliveryAttempt.attempt_count)
        )
        result = await session.execute(stmt)
        claimed_attempt_count = result.scalar_one_or_none()
        return int(claimed_attempt_count) if claimed_attempt_count is not None else None

    @staticmethod
    async def claim_pending_replay_dispatch(
        session: AsyncSession,
        *,
        idempotency_key: str,
        expected_attempt_count: int,
    ) -> int | None:
        stmt = (
            update(TelegramDeliveryAttempt)
            .where(
                TelegramDeliveryAttempt.idempotency_key == idempotency_key,
                TelegramDeliveryAttempt.status == "PENDING",
                TelegramDeliveryAttempt.attempt_count == expected_attempt_count,
            )
            .values(
                attempt_count=TelegramDeliveryAttempt.attempt_count + 1,
                failure_code=None,
                failure_reason=None,
                telegram_error_code=None,
                updated_at=func.now(),
            )
            .returning(TelegramDeliveryAttempt.attempt_count)
        )
        result = await session.execute(stmt)
        dispatched_attempt_count = result.scalar_one_or_none()
        return int(dispatched_attempt_count) if dispatched_attempt_count is not None else None
