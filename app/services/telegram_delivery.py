from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.production_reliability_types import TelegramDeliveryAttemptCreate
from app.db.repo.telegram_delivery_attempts_repo import TelegramDeliveryAttemptsRepo
from app.db.repo.telegram_delivery_retry_repo import TelegramDeliveryRetryRepo
from app.services.telegram_delivery_outcomes import (
    TELEGRAM_DELIVERY_TERMINAL_STATUSES,
    TelegramDeliveryOutcome,
    TelegramDeliveryOutcomeStatus,
    TelegramDeliverySkip,
    classify_telegram_delivery_exception,
)

TelegramDeliverySend = Callable[[], Awaitable[object]]


@dataclass(frozen=True, slots=True)
class _PreparedDelivery:
    created: bool
    replayed: bool


async def deliver_telegram_once(
    session_local: Any,
    *,
    attempt: TelegramDeliveryAttemptCreate,
    send: TelegramDeliverySend,
    skip: TelegramDeliverySkip | None = None,
    allow_pending_replay_send: bool = False,
    allow_stale_pending_replay_send: bool = False,
    retry_claim_ttl_seconds: int = 300,
    attempts_repo: Any = TelegramDeliveryAttemptsRepo,
) -> TelegramDeliveryOutcome:
    async with session_local.begin() as session:
        prepared = await _prepare_delivery_attempt(
            session,
            attempt=attempt,
            skip=skip,
            allow_pending_replay_send=allow_pending_replay_send,
            allow_stale_pending_replay_send=allow_stale_pending_replay_send,
            pending_replay_ttl_seconds=retry_claim_ttl_seconds,
            attempts_repo=attempts_repo,
        )
        if isinstance(prepared, TelegramDeliveryOutcome):
            return prepared

    try:
        await send()
    except Exception as exc:
        return await _record_send_exception(
            session_local,
            exc=exc,
            idempotency_key=attempt.idempotency_key,
            prepared=prepared,
            retry_claim_ttl_seconds=retry_claim_ttl_seconds,
            attempts_repo=attempts_repo,
        )

    async with session_local.begin() as session:
        await attempts_repo.mark_sent(session, idempotency_key=attempt.idempotency_key)
    return TelegramDeliveryOutcome(
        status="SENT",
        created=prepared.created,
        attempted=True,
        replayed=prepared.replayed,
    )


async def _prepare_delivery_attempt(
    session: AsyncSession,
    *,
    attempt: TelegramDeliveryAttemptCreate,
    skip: TelegramDeliverySkip | None,
    allow_pending_replay_send: bool,
    allow_stale_pending_replay_send: bool,
    pending_replay_ttl_seconds: int,
    attempts_repo: Any,
) -> TelegramDeliveryOutcome | _PreparedDelivery:
    row, created = await attempts_repo.create_once(session, attempt=attempt)
    current_status = str(getattr(row, "status", "PENDING"))
    replayed = not created

    if current_status in TELEGRAM_DELIVERY_TERMINAL_STATUSES:
        return _terminal_replay_outcome(row=row, status=current_status, created=created)
    if replayed and current_status == "PENDING":
        if not await _can_replay_pending(
            session=session,
            allow_pending_replay_send=allow_pending_replay_send,
            allow_stale_pending_replay_send=allow_stale_pending_replay_send,
            idempotency_key=attempt.idempotency_key,
            pending_replay_ttl_seconds=pending_replay_ttl_seconds,
            attempts_repo=attempts_repo,
        ):
            return _pending_replay_outcome(created=created)

    if skip is not None:
        await attempts_repo.mark_skipped(
            session,
            idempotency_key=attempt.idempotency_key,
            failure_code=skip.failure_code,
            failure_reason=skip.failure_reason,
        )
        return _skipped_outcome(created=created, replayed=replayed, skip=skip)

    return _PreparedDelivery(created=created, replayed=replayed)


async def _can_replay_pending(
    *,
    session: AsyncSession,
    allow_pending_replay_send: bool,
    allow_stale_pending_replay_send: bool,
    idempotency_key: str,
    pending_replay_ttl_seconds: int,
    attempts_repo: Any,
) -> bool:
    if allow_pending_replay_send:
        return True
    if not allow_stale_pending_replay_send:
        return False
    return await attempts_repo.claim_stale_pending_replay(
        session,
        idempotency_key=idempotency_key,
        claim_ttl_seconds=pending_replay_ttl_seconds,
    )


def _terminal_replay_outcome(
    *,
    row: object,
    status: str,
    created: bool,
) -> TelegramDeliveryOutcome:
    return TelegramDeliveryOutcome(
        status=cast(TelegramDeliveryOutcomeStatus, status),
        created=created,
        attempted=False,
        replayed=not created,
        failure_code=getattr(row, "failure_code", None),
        failure_reason=getattr(row, "failure_reason", None),
        telegram_error_code=getattr(row, "telegram_error_code", None),
    )


def _pending_replay_outcome(*, created: bool) -> TelegramDeliveryOutcome:
    return TelegramDeliveryOutcome(
        status="RETRY",
        created=created,
        attempted=False,
        replayed=not created,
        failure_code="PENDING_REPLAY",
    )


def _skipped_outcome(
    *,
    created: bool,
    replayed: bool,
    skip: TelegramDeliverySkip,
) -> TelegramDeliveryOutcome:
    return TelegramDeliveryOutcome(
        status="SKIPPED",
        created=created,
        attempted=False,
        replayed=replayed,
        failure_code=skip.failure_code,
        failure_reason=skip.failure_reason,
    )


async def _record_send_exception(
    session_local: Any,
    *,
    exc: Exception,
    idempotency_key: str,
    prepared: _PreparedDelivery,
    retry_claim_ttl_seconds: int,
    attempts_repo: Any,
) -> TelegramDeliveryOutcome:
    classified = classify_telegram_delivery_exception(exc)
    if classified is None:
        raise exc
    if classified.status == "RETRY":
        async with session_local.begin() as session:
            return await _defer_retry_after(
                session,
                idempotency_key=idempotency_key,
                created=prepared.created,
                replayed=prepared.replayed,
                retry_after_seconds=classified.retry_after_seconds,
                retry_claim_ttl_seconds=retry_claim_ttl_seconds,
                attempts_repo=attempts_repo,
            )
    if classified.failure is None:
        raise exc

    async with session_local.begin() as session:
        await attempts_repo.mark_failed(
            session,
            idempotency_key=idempotency_key,
            failure=classified.failure,
        )
    return TelegramDeliveryOutcome(
        status="FAILED",
        created=prepared.created,
        attempted=True,
        replayed=prepared.replayed,
        failure_code=classified.failure.failure_code,
        failure_reason=classified.failure.failure_reason,
        telegram_error_code=classified.failure.telegram_error_code,
    )


async def _defer_retry_after(
    session: AsyncSession,
    *,
    idempotency_key: str,
    created: bool,
    replayed: bool,
    retry_after_seconds: int | None,
    retry_claim_ttl_seconds: int,
    attempts_repo: Any,
) -> TelegramDeliveryOutcome:
    retry_after = max(1, int(retry_after_seconds or 1))
    await attempts_repo.defer_retry_after(
        session,
        idempotency_key=idempotency_key,
        retry_after_seconds=retry_after,
        claim_ttl_seconds=retry_claim_ttl_seconds,
    )
    return TelegramDeliveryOutcome(
        status="RETRY",
        created=created,
        attempted=True,
        replayed=replayed,
        retry_after_seconds=retry_after,
    )


async def claim_telegram_delivery_retries(
    session: AsyncSession,
    *,
    flow: str,
    limit: int,
    claim_ttl_seconds: int = 300,
    retry_repo: Any = TelegramDeliveryRetryRepo,
) -> list[object]:
    return await retry_repo.claim_pending_batch(
        session,
        flow=flow,
        limit=limit,
        claim_ttl_seconds=claim_ttl_seconds,
    )
