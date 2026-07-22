from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Unpack

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.production_reliability_types import TelegramDeliveryAttemptCreate
from app.db.repo.telegram_delivery_attempts_repo import TelegramDeliveryAttemptsRepo
from app.db.repo.telegram_delivery_retry_repo import TelegramDeliveryRetryRepo
from app.services.telegram_delivery_lease import (
    TelegramDeliveryCallOptions,
    TelegramDeliveryLease,
    TelegramDeliveryReplayPolicy,
    claim_pending_replay,
    defer_retry_after,
    lease_cas_enabled,
    lease_update_kwargs,
    require_lease_update,
    resolve_call_options,
    row_attempt_count,
)
from app.services.telegram_delivery_outcomes import (
    TELEGRAM_DELIVERY_TERMINAL_STATUSES,
    TelegramDeliveryOutcome,
    TelegramDeliverySkip,
    classify_telegram_delivery_exception,
    pending_replay_outcome,
    skipped_outcome,
    terminal_replay_outcome,
)

TelegramDeliverySend = Callable[[], Awaitable[object]]


async def deliver_telegram_once(
    session_local: Any,
    *,
    attempt: TelegramDeliveryAttemptCreate,
    send: TelegramDeliverySend,
    skip: TelegramDeliverySkip | None = None,
    **options: Unpack[TelegramDeliveryCallOptions],
) -> TelegramDeliveryOutcome:
    attempts_repo, retry_claim_ttl_seconds, replay_policy = resolve_call_options(options)
    attempts_repo = attempts_repo or TelegramDeliveryAttemptsRepo
    async with session_local.begin() as session:
        prepared = await _prepare_delivery_attempt(
            session,
            attempt=attempt,
            skip=skip,
            replay_policy=replay_policy,
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
        updated = await attempts_repo.mark_sent(
            session,
            idempotency_key=attempt.idempotency_key,
            **lease_update_kwargs(prepared, attempts_repo),
        )
        require_lease_update(updated=updated, status="sent", attempts_repo=attempts_repo)
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
    replay_policy: TelegramDeliveryReplayPolicy,
    attempts_repo: Any,
) -> TelegramDeliveryOutcome | TelegramDeliveryLease:
    row, created = await attempts_repo.create_once(session, attempt=attempt)
    current_status = str(getattr(row, "status", "PENDING"))
    replayed = not created
    lease_attempt_count = (
        row_attempt_count(row, required=lease_cas_enabled(attempts_repo)) if created else None
    )

    if current_status in TELEGRAM_DELIVERY_TERMINAL_STATUSES:
        return terminal_replay_outcome(row=row, status=current_status, created=created)
    if replayed and current_status == "PENDING":
        lease_attempt_count = await claim_pending_replay(
            session=session,
            row=row,
            policy=replay_policy,
            idempotency_key=attempt.idempotency_key,
            attempts_repo=attempts_repo,
        )
        if lease_attempt_count is None:
            return pending_replay_outcome(created=created)

    if skip is not None:
        prepared = TelegramDeliveryLease(created, replayed, lease_attempt_count)
        updated = await attempts_repo.mark_skipped(
            session,
            idempotency_key=attempt.idempotency_key,
            failure_code=skip.failure_code,
            failure_reason=skip.failure_reason,
            **lease_update_kwargs(prepared, attempts_repo),
        )
        require_lease_update(updated=updated, status="skipped", attempts_repo=attempts_repo)
        return skipped_outcome(created=created, replayed=replayed, skip=skip)

    return TelegramDeliveryLease(created, replayed, lease_attempt_count)


async def _record_send_exception(
    session_local: Any,
    *,
    exc: Exception,
    idempotency_key: str,
    prepared: TelegramDeliveryLease,
    retry_claim_ttl_seconds: int,
    attempts_repo: Any,
) -> TelegramDeliveryOutcome:
    classified = classify_telegram_delivery_exception(exc)
    if classified is None:
        raise exc
    if classified.status == "RETRY":
        async with session_local.begin() as session:
            return await defer_retry_after(
                session,
                idempotency_key=idempotency_key,
                prepared=prepared,
                retry_after_seconds=classified.retry_after_seconds,
                retry_claim_ttl_seconds=retry_claim_ttl_seconds,
                attempts_repo=attempts_repo,
            )
    if classified.failure is None:
        raise exc

    async with session_local.begin() as session:
        updated = await attempts_repo.mark_failed(
            session,
            idempotency_key=idempotency_key,
            failure=classified.failure,
            **lease_update_kwargs(prepared, attempts_repo),
        )
        require_lease_update(updated=updated, status="failed", attempts_repo=attempts_repo)
    return TelegramDeliveryOutcome(
        status="FAILED",
        created=prepared.created,
        attempted=True,
        replayed=prepared.replayed,
        failure_code=classified.failure.failure_code,
        failure_reason=classified.failure.failure_reason,
        telegram_error_code=classified.failure.telegram_error_code,
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
