from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.production_reliability import (
    ProductionInvariantAlert,
    TelegramDeliveryAttempt,
    WorkerTaskHeartbeat,
)

DELIVERY_STATUS_PENDING = "PENDING"
DELIVERY_STATUS_SENT = "SENT"
DELIVERY_STATUS_FAILED = "FAILED"
DELIVERY_STATUS_SKIPPED = "SKIPPED"


def hash_chat_id(chat_id: int | str) -> str:
    return hashlib.sha256(str(chat_id).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DeliveryAttemptCreate:
    flow: str
    task_name: str
    correlation_id: str
    idempotency_key: str
    target_type: str
    target_id: str
    telegram_user_id: int | None = None
    chat_id_hash: str | None = None
    safe_context: dict[str, object] | None = None


class TelegramDeliveryAttemptsRepo:
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

    @staticmethod
    async def has_blocked_candidate(
        session: AsyncSession,
        *,
        telegram_user_id: int,
    ) -> bool:
        stmt = (
            select(TelegramDeliveryAttempt.id)
            .where(
                TelegramDeliveryAttempt.telegram_user_id == telegram_user_id,
                TelegramDeliveryAttempt.status == DELIVERY_STATUS_FAILED,
                TelegramDeliveryAttempt.is_blocked_candidate.is_(True),
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None


class WorkerTaskHeartbeatsRepo:
    @staticmethod
    async def record_started(
        session: AsyncSession,
        *,
        task_name: str,
        schedule_key: str,
        started_at: datetime,
    ) -> None:
        stmt = (
            insert(WorkerTaskHeartbeat)
            .values(
                task_name=task_name,
                schedule_key=schedule_key,
                last_started_at=started_at,
                updated_at=started_at,
            )
            .on_conflict_do_update(
                index_elements=[WorkerTaskHeartbeat.task_name, WorkerTaskHeartbeat.schedule_key],
                set_={
                    "last_started_at": started_at,
                    "updated_at": started_at,
                },
            )
        )
        await session.execute(stmt)

    @staticmethod
    async def record_success(
        session: AsyncSession,
        *,
        task_name: str,
        schedule_key: str,
        succeeded_at: datetime,
        duration_ms: int,
    ) -> None:
        stmt = (
            insert(WorkerTaskHeartbeat)
            .values(
                task_name=task_name,
                schedule_key=schedule_key,
                last_started_at=succeeded_at,
                last_success_at=succeeded_at,
                last_duration_ms=duration_ms,
                consecutive_failures=0,
                updated_at=succeeded_at,
            )
            .on_conflict_do_update(
                index_elements=[WorkerTaskHeartbeat.task_name, WorkerTaskHeartbeat.schedule_key],
                set_={
                    "last_success_at": succeeded_at,
                    "last_duration_ms": duration_ms,
                    "last_error_hash": None,
                    "consecutive_failures": 0,
                    "updated_at": succeeded_at,
                },
            )
        )
        await session.execute(stmt)

    @staticmethod
    async def record_failure(
        session: AsyncSession,
        *,
        task_name: str,
        schedule_key: str,
        failed_at: datetime,
        duration_ms: int,
        error_hash: str,
    ) -> None:
        stmt = (
            insert(WorkerTaskHeartbeat)
            .values(
                task_name=task_name,
                schedule_key=schedule_key,
                last_started_at=failed_at,
                last_failed_at=failed_at,
                last_duration_ms=duration_ms,
                last_error_hash=error_hash,
                consecutive_failures=1,
                updated_at=failed_at,
            )
            .on_conflict_do_update(
                index_elements=[WorkerTaskHeartbeat.task_name, WorkerTaskHeartbeat.schedule_key],
                set_={
                    "last_failed_at": failed_at,
                    "last_duration_ms": duration_ms,
                    "last_error_hash": error_hash,
                    "consecutive_failures": WorkerTaskHeartbeat.consecutive_failures + 1,
                    "updated_at": failed_at,
                },
            )
        )
        await session.execute(stmt)


class ProductionInvariantAlertsRepo:
    @staticmethod
    async def record_open(
        session: AsyncSession,
        *,
        severity: str,
        alert_type: str,
        correlation_key: str,
        seen_at: datetime,
        safe_context: dict[str, object],
    ) -> None:
        await ProductionInvariantAlertsRepo._reopen_existing_terminal(
            session,
            severity=severity,
            alert_type=alert_type,
            correlation_key=correlation_key,
            seen_at=seen_at,
            safe_context=safe_context,
        )
        stmt = (
            insert(ProductionInvariantAlert)
            .values(
                severity=severity,
                type=alert_type,
                correlation_key=correlation_key,
                status="OPEN",
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                safe_context=safe_context,
                count=1,
                updated_at=seen_at,
            )
            .on_conflict_do_update(
                index_elements=[
                    ProductionInvariantAlert.type,
                    ProductionInvariantAlert.correlation_key,
                    ProductionInvariantAlert.status,
                ],
                set_={
                    "severity": severity,
                    "last_seen_at": seen_at,
                    "safe_context": safe_context,
                    "count": ProductionInvariantAlert.count + 1,
                    "updated_at": seen_at,
                },
            )
        )
        await session.execute(stmt)

    @staticmethod
    async def _reopen_existing_terminal(
        session: AsyncSession,
        *,
        severity: str,
        alert_type: str,
        correlation_key: str,
        seen_at: datetime,
        safe_context: dict[str, object],
    ) -> int:
        open_stmt = select(ProductionInvariantAlert.id).where(
            ProductionInvariantAlert.type == alert_type,
            ProductionInvariantAlert.correlation_key == correlation_key,
            ProductionInvariantAlert.status == "OPEN",
        )
        open_result = await session.execute(open_stmt)
        if open_result.scalar_one_or_none() is not None:
            return 0

        terminal_stmt = (
            select(ProductionInvariantAlert.id)
            .where(
                ProductionInvariantAlert.type == alert_type,
                ProductionInvariantAlert.correlation_key == correlation_key,
                ProductionInvariantAlert.status.in_(("RESOLVED", "ACKED")),
            )
            .order_by(
                ProductionInvariantAlert.updated_at.desc(), ProductionInvariantAlert.id.desc()
            )
            .limit(1)
        )
        terminal_result = await session.execute(terminal_stmt)
        alert_id = terminal_result.scalar_one_or_none()
        if alert_id is None:
            return 0

        stmt = (
            update(ProductionInvariantAlert)
            .where(ProductionInvariantAlert.id == alert_id)
            .values(
                severity=severity,
                status="OPEN",
                last_seen_at=seen_at,
                resolved_at=None,
                acked_at=None,
                safe_context=safe_context,
                count=ProductionInvariantAlert.count + 1,
                updated_at=seen_at,
            )
        )
        result = await session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    @staticmethod
    async def mark_resolved(
        session: AsyncSession,
        *,
        alert_type: str,
        correlation_key: str,
        resolved_at: datetime,
    ) -> int:
        stmt = (
            update(ProductionInvariantAlert)
            .where(
                ProductionInvariantAlert.type == alert_type,
                ProductionInvariantAlert.correlation_key == correlation_key,
                ProductionInvariantAlert.status == "OPEN",
            )
            .values(status="RESOLVED", resolved_at=resolved_at, updated_at=resolved_at)
        )
        result = await session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)


def safe_error_hash(value: BaseException | str) -> str:
    payload = value if isinstance(value, str) else f"{type(value).__name__}:{value}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compiled_sql(statement: Any) -> str:
    return str(statement)
