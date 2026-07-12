from __future__ import annotations

from app.db.repo.production_reliability_repo import TelegramDeliveryAttemptsRepo, hash_chat_id
from app.services.telegram_delivery_errors import classify_telegram_delivery_exception
from app.services.telegram_delivery_outcomes import (
    mark_telegram_delivery_failed,
    mark_telegram_delivery_failed_with_classification,
    mark_telegram_delivery_sent,
    record_telegram_delivery_skipped,
)
from app.services.telegram_delivery_preparation import prepare_telegram_delivery
from app.services.telegram_delivery_retry import begin_telegram_delivery_dispatch
from app.services.telegram_delivery_types import (
    BLOCKED_CANDIDATE_TTL,
    FAILURE_CODE_BAD_REQUEST,
    FAILURE_CODE_BLOCKED,
    FAILURE_CODE_FORBIDDEN,
    FAILURE_CODE_RETRY_AFTER,
    FAILURE_CODE_TRANSIENT,
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

__all__ = [
    "BLOCKED_CANDIDATE_TTL",
    "FAILURE_CODE_BAD_REQUEST",
    "FAILURE_CODE_BLOCKED",
    "FAILURE_CODE_FORBIDDEN",
    "FAILURE_CODE_RETRY_AFTER",
    "FAILURE_CODE_TRANSIENT",
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
    "begin_telegram_delivery_dispatch",
    "classify_telegram_delivery_exception",
    "hash_chat_id",
    "mark_telegram_delivery_failed",
    "mark_telegram_delivery_failed_with_classification",
    "mark_telegram_delivery_sent",
    "prepare_telegram_delivery",
    "record_telegram_delivery_skipped",
]
