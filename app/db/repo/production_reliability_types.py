from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

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


def safe_error_hash(value: BaseException | str) -> str:
    payload = value if isinstance(value, str) else f"{type(value).__name__}:{value}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compiled_sql(statement: Any) -> str:
    return str(statement)
