from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

FAILURE_CODE_BLOCKED = "TELEGRAM_BLOCKED_CANDIDATE"
FAILURE_CODE_FORBIDDEN = "TELEGRAM_FORBIDDEN"
FAILURE_CODE_BAD_REQUEST = "TELEGRAM_BAD_REQUEST"
FAILURE_CODE_RETRY_AFTER = "TELEGRAM_RETRY_AFTER"
FAILURE_CODE_TRANSIENT = "TELEGRAM_TRANSIENT_SEND_ERROR"
FAILURE_CODE_UNKNOWN = "TELEGRAM_SEND_ERROR"
SKIP_CODE_DUPLICATE = "DUPLICATE_DELIVERY_ATTEMPT"
SKIP_CODE_NO_CHAT = "MISSING_CHAT_ID"
SKIP_CODE_EDIT_REPLACED_BY_SEND = "EDIT_REPLACED_BY_FALLBACK_SEND"
RETRYABLE_FAILURE_CODES = frozenset({FAILURE_CODE_RETRY_AFTER, FAILURE_CODE_TRANSIENT})
STALE_PENDING_AFTER = timedelta(minutes=15)
BLOCKED_CANDIDATE_TTL = timedelta(days=30)
MAX_DELIVERY_ATTEMPTS = 3
PENDING_REPLAY_SAFE_CONTEXT_KEY = "pending_replay_safe"


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
