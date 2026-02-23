from __future__ import annotations

import random

import structlog

from app.db.repo.outbox_events_repo import OutboxEventsRepo
from app.db.session import SessionLocal
from app.workers.tasks.telegram_updates_config import RETRY_JITTER_RATIO

logger = structlog.get_logger("app.workers.tasks.telegram_updates")


def retry_backoff_seconds(
    *,
    next_retry_attempt: int,
    backoff_max_seconds: int,
) -> int:
    safe_retry_attempt = max(1, int(next_retry_attempt))
    safe_backoff_max_seconds = max(1, int(backoff_max_seconds))

    base_delay = min(
        safe_backoff_max_seconds,
        2 ** (safe_retry_attempt - 1),
    )
    max_jitter = max(0, int(base_delay * RETRY_JITTER_RATIO))
    jitter = random.randint(0, max_jitter) if max_jitter > 0 else 0
    return min(safe_backoff_max_seconds, base_delay + jitter)


async def emit_reliability_event(
    *,
    event_type: str,
    payload: dict[str, object],
) -> None:
    try:
        async with SessionLocal.begin() as session:
            await OutboxEventsRepo.create(
                session,
                event_type=event_type,
                payload=payload,
                status="SENT",
            )
    except Exception:
        logger.exception(
            "telegram_update_reliability_event_write_failed",
            event_type=event_type,
            payload=payload,
        )
