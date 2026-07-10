from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from app.db.repo.production_reliability_repo import (
    DeliveryAttemptCreate,
    TelegramDeliveryAttemptsRepo,
    hash_chat_id,
)
from app.db.session import SessionLocal

FAILURE_CODE_BLOCKED = "TELEGRAM_BLOCKED_CANDIDATE"
FAILURE_CODE_FORBIDDEN = "TELEGRAM_FORBIDDEN"
FAILURE_CODE_BAD_REQUEST = "TELEGRAM_BAD_REQUEST"
FAILURE_CODE_RETRY_AFTER = "TELEGRAM_RETRY_AFTER"
FAILURE_CODE_UNKNOWN = "TELEGRAM_SEND_ERROR"
SKIP_CODE_DUPLICATE = "DUPLICATE_DELIVERY_ATTEMPT"
SKIP_CODE_NO_CHAT = "MISSING_CHAT_ID"


@dataclass(frozen=True, slots=True)
class TelegramDeliveryTarget:
    flow: str
    task_name: str
    correlation_id: str
    target_type: str
    target_id: str
    idempotency_key: str
    telegram_user_id: int | None
    chat_id: int | None
    safe_context: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class DeliveryPreparation:
    idempotency_key: str
    should_send: bool
    status: str
    created: bool


@dataclass(frozen=True, slots=True)
class TelegramDeliveryFailure:
    failure_code: str
    failure_reason: str
    telegram_error_code: int | None
    is_blocked_candidate: bool


def build_delivery_idempotency_key(
    *,
    flow: str,
    correlation_id: str,
    target_type: str,
    target_id: str,
) -> str:
    return f"telegram-delivery:{flow}:{correlation_id}:{target_type}:{target_id}"


async def prepare_telegram_delivery(
    *,
    target: TelegramDeliveryTarget,
    happened_at: datetime,
    session_local: Any = SessionLocal,
) -> DeliveryPreparation:
    if target.chat_id is None:
        return await _record_skipped(
            target=target,
            happened_at=happened_at,
            failure_code=SKIP_CODE_NO_CHAT,
            failure_reason="target has no chat id",
            session_local=session_local,
        )

    async with session_local.begin() as session:
        if (
            target.telegram_user_id is not None
            and await TelegramDeliveryAttemptsRepo.has_blocked_candidate(
                session,
                telegram_user_id=target.telegram_user_id,
            )
        ):
            attempt, created = await TelegramDeliveryAttemptsRepo.create_pending_once(
                session,
                item=_attempt_create(target),
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
            item=_attempt_create(target),
        )
        return DeliveryPreparation(
            idempotency_key=target.idempotency_key,
            should_send=created,
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
    return await _record_skipped(
        target=target,
        happened_at=happened_at,
        failure_code=failure_code,
        failure_reason=failure_reason,
        session_local=session_local,
    )


def classify_telegram_delivery_exception(exc: BaseException) -> TelegramDeliveryFailure:
    message = _safe_exception_label(exc)
    if isinstance(exc, TelegramForbiddenError):
        return TelegramDeliveryFailure(
            failure_code=FAILURE_CODE_FORBIDDEN,
            failure_reason=message,
            telegram_error_code=403,
            is_blocked_candidate=True,
        )
    if isinstance(exc, TelegramBadRequest):
        return TelegramDeliveryFailure(
            failure_code=FAILURE_CODE_BAD_REQUEST,
            failure_reason=message,
            telegram_error_code=400,
            is_blocked_candidate=_looks_like_missing_chat(exc),
        )
    if isinstance(exc, TelegramRetryAfter):
        return TelegramDeliveryFailure(
            failure_code=FAILURE_CODE_RETRY_AFTER,
            failure_reason=message,
            telegram_error_code=429,
            is_blocked_candidate=False,
        )
    return TelegramDeliveryFailure(
        failure_code=FAILURE_CODE_UNKNOWN,
        failure_reason=message,
        telegram_error_code=None,
        is_blocked_candidate=False,
    )


async def _record_skipped(
    *,
    target: TelegramDeliveryTarget,
    happened_at: datetime,
    failure_code: str,
    failure_reason: str,
    session_local: Any,
) -> DeliveryPreparation:
    async with session_local.begin() as session:
        attempt, created = await TelegramDeliveryAttemptsRepo.create_pending_once(
            session,
            item=_attempt_create(target),
        )
        if created or attempt.status == "PENDING":
            await TelegramDeliveryAttemptsRepo.mark_skipped(
                session,
                idempotency_key=target.idempotency_key,
                skipped_at=happened_at,
                failure_code=failure_code,
                failure_reason=failure_reason,
            )
        return DeliveryPreparation(
            idempotency_key=target.idempotency_key,
            should_send=False,
            status="SKIPPED",
            created=created,
        )


def _attempt_create(target: TelegramDeliveryTarget) -> DeliveryAttemptCreate:
    return DeliveryAttemptCreate(
        flow=target.flow,
        task_name=target.task_name,
        correlation_id=target.correlation_id,
        idempotency_key=target.idempotency_key,
        target_type=target.target_type,
        target_id=target.target_id,
        telegram_user_id=target.telegram_user_id,
        chat_id_hash=hash_chat_id(target.chat_id) if target.chat_id is not None else None,
        safe_context=target.safe_context,
    )


def _safe_exception_label(exc: BaseException) -> str:
    return type(exc).__name__


def _looks_like_missing_chat(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "chat not found" in text or "bot was blocked" in text
