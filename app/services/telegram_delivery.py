from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.repo.production_reliability_repo import TelegramDeliveryAttemptsRepo, hash_chat_id
from app.db.session import SessionLocal
from app.services.telegram_delivery_errors import classify_telegram_delivery_exception
from app.services.telegram_delivery_records import attempt_create, record_skipped
from app.services.telegram_delivery_retry import claim_controlled_retry
from app.services.telegram_delivery_types import (
    BLOCKED_CANDIDATE_TTL,
    FAILURE_CODE_BAD_REQUEST,
    FAILURE_CODE_BLOCKED,
    FAILURE_CODE_FORBIDDEN,
    FAILURE_CODE_RETRY_AFTER,
    FAILURE_CODE_UNKNOWN,
    MAX_DELIVERY_ATTEMPTS,
    PENDING_REPLAY_SAFE_CONTEXT_KEY,
    RETRYABLE_FAILURE_CODES,
    SKIP_CODE_DUPLICATE,
    SKIP_CODE_EDIT_REPLACED_BY_SEND,
    SKIP_CODE_NO_CHAT,
    STALE_PENDING_AFTER,
    DeliveryPreparation,
    TelegramDeliveryFailure,
    TelegramDeliveryTarget,
    build_delivery_idempotency_key,
)


async def prepare_telegram_delivery(
    *,
    target: TelegramDeliveryTarget,
    happened_at: datetime,
    session_local: Any = SessionLocal,
) -> DeliveryPreparation:
    if target.chat_id is None:
        return await record_skipped(
            target=target,
            happened_at=happened_at,
            failure_code=SKIP_CODE_NO_CHAT,
            failure_reason="target has no chat id",
            session_local=session_local,
            attempts_repo=TelegramDeliveryAttemptsRepo,
        )

    async with session_local.begin() as session:
        if (
            target.telegram_user_id is not None
            and await TelegramDeliveryAttemptsRepo.has_blocked_candidate(
                session,
                telegram_user_id=target.telegram_user_id,
                blocked_since=happened_at - BLOCKED_CANDIDATE_TTL,
            )
        ):
            attempt, created = await TelegramDeliveryAttemptsRepo.create_pending_once(
                session,
                item=attempt_create(target),
            )
            if created or attempt.status == "PENDING":
                await TelegramDeliveryAttemptsRepo.mark_skipped(
                    session,
                    idempotency_key=target.idempotency_key,
                    skipped_at=happened_at,
                    failure_code=FAILURE_CODE_BLOCKED,
                    failure_reason="known blocked candidate",
                )
            return DeliveryPreparation(
                idempotency_key=target.idempotency_key,
                should_send=False,
                status="SKIPPED",
                created=created,
            )

        attempt, created = await TelegramDeliveryAttemptsRepo.create_pending_once(
            session,
            item=attempt_create(target),
        )
        should_send = created or await claim_controlled_retry(
            session,
            idempotency_key=target.idempotency_key,
            happened_at=happened_at,
            attempt=attempt,
            attempts_repo=TelegramDeliveryAttemptsRepo,
        )
        return DeliveryPreparation(
            idempotency_key=target.idempotency_key,
            should_send=should_send,
            status=str(attempt.status),
            created=created,
        )


async def mark_telegram_delivery_sent(
    *,
    idempotency_key: str,
    happened_at: datetime,
    session_local: Any = SessionLocal,
) -> None:
    async with session_local.begin() as session:
        await TelegramDeliveryAttemptsRepo.mark_sent(
            session,
            idempotency_key=idempotency_key,
            sent_at=happened_at,
        )


async def mark_telegram_delivery_failed(
    *,
    idempotency_key: str,
    happened_at: datetime,
    exc: BaseException,
    session_local: Any = SessionLocal,
) -> TelegramDeliveryFailure:
    failure = classify_telegram_delivery_exception(exc)
    async with session_local.begin() as session:
        await TelegramDeliveryAttemptsRepo.mark_failed(
            session,
            idempotency_key=idempotency_key,
            failed_at=happened_at,
            failure_code=failure.failure_code,
            failure_reason=failure.failure_reason,
            telegram_error_code=failure.telegram_error_code,
            is_blocked_candidate=failure.is_blocked_candidate,
        )
    return failure


async def record_telegram_delivery_skipped(
    *,
    target: TelegramDeliveryTarget,
    happened_at: datetime,
    failure_code: str,
    failure_reason: str,
    session_local: Any = SessionLocal,
) -> DeliveryPreparation:
    return await record_skipped(
        target=target,
        happened_at=happened_at,
        failure_code=failure_code,
        failure_reason=failure_reason,
        session_local=session_local,
        attempts_repo=TelegramDeliveryAttemptsRepo,
    )


__all__ = [
    "BLOCKED_CANDIDATE_TTL",
    "FAILURE_CODE_BAD_REQUEST",
    "FAILURE_CODE_BLOCKED",
    "FAILURE_CODE_FORBIDDEN",
    "FAILURE_CODE_RETRY_AFTER",
    "FAILURE_CODE_UNKNOWN",
    "MAX_DELIVERY_ATTEMPTS",
    "PENDING_REPLAY_SAFE_CONTEXT_KEY",
    "RETRYABLE_FAILURE_CODES",
    "SKIP_CODE_DUPLICATE",
    "SKIP_CODE_EDIT_REPLACED_BY_SEND",
    "SKIP_CODE_NO_CHAT",
    "STALE_PENDING_AFTER",
    "DeliveryPreparation",
    "TelegramDeliveryAttemptsRepo",
    "TelegramDeliveryFailure",
    "TelegramDeliveryTarget",
    "build_delivery_idempotency_key",
    "classify_telegram_delivery_exception",
    "hash_chat_id",
    "mark_telegram_delivery_failed",
    "mark_telegram_delivery_sent",
    "prepare_telegram_delivery",
    "record_telegram_delivery_skipped",
]
