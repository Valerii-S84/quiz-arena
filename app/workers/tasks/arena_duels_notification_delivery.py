from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.analytics_events import BERLIN_TIMEZONE
from app.game.arena_duels.constants import ARENA_BEATEN_NOTIFICATION_EVENT
from app.game.arena_duels.types import ArenaBeatenNotification
from app.services.telegram_delivery import deliver_telegram_once
from app.services.telegram_delivery_outcomes import TelegramDeliveryOutcome, TelegramDeliverySkip
from app.workers.tasks.arena_duels_notification_delivery_queries import (
    ArenaBeatenNotificationDeps,
    load_notification_users,
    notification_already_sent,
)
from app.workers.tasks.arena_duels_notification_delivery_target import beaten_delivery_attempt
from app.workers.tasks.arena_duels_notification_payload import notification_payload
from app.workers.tasks.arena_duels_notification_sender import send_notification_message

_PENDING_REPLAY_CLAIM_TTL_SECONDS = 300
_SKIP_CODE_DUPLICATE = "DUPLICATE"
_SKIP_CODE_MISSING_TARGET_USER = "MISSING_TARGET_USER"


async def send_arena_beaten_notification_with_bot(
    *,
    bot,
    notification: ArenaBeatenNotification,
    happened_at: datetime,
    source: str,
    deps: ArenaBeatenNotificationDeps,
) -> dict[str, int]:
    payload = notification_payload(notification)
    local_date_berlin = happened_at.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date()

    async with deps.session_local.begin() as session:
        if await notification_already_sent(session, notification, payload, deps):
            return await _record_skipped_notification(
                notification=notification,
                failure_code=_SKIP_CODE_DUPLICATE,
                failure_reason="beaten notification analytics event already exists",
                deps=deps,
            )

        previous_user, new_best_user = await load_notification_users(
            session,
            notification,
            deps,
        )
        if previous_user is None:
            return await _record_skipped_notification(
                notification=notification,
                failure_code=_SKIP_CODE_MISSING_TARGET_USER,
                failure_reason="target user missing",
                deps=deps,
            )

        outcome = await _deliver_notification(
            bot=bot,
            notification=notification,
            previous_user=previous_user,
            new_best_user=new_best_user,
            deps=deps,
        )
        if outcome.status != "SENT":
            return _result_for_delivery_outcome(outcome)

        await deps.analytics_repo.create_arena_beaten_notification_event_once(
            session,
            event_type=ARENA_BEATEN_NOTIFICATION_EVENT,
            source=source,
            user_id=notification.previous_best_user_id,
            local_date_berlin=local_date_berlin,
            payload=payload,
            happened_at=happened_at,
        )

    return _result_for_delivery_outcome(outcome)


async def _deliver_notification(
    *,
    bot,
    notification: ArenaBeatenNotification,
    previous_user,
    new_best_user,
    deps: ArenaBeatenNotificationDeps,
) -> TelegramDeliveryOutcome:
    async def _send() -> None:
        await send_notification_message(
            bot,
            notification,
            previous_user,
            new_best_user,
        )

    return await deliver_telegram_once(
        deps.session_local,
        attempt=beaten_delivery_attempt(
            notification=notification,
            telegram_user_id=int(previous_user.telegram_user_id),
        ),
        send=_send,
        allow_stale_pending_replay_send=True,
        retry_claim_ttl_seconds=_PENDING_REPLAY_CLAIM_TTL_SECONDS,
    )


async def _record_skipped_notification(
    *,
    notification: ArenaBeatenNotification,
    failure_code: str,
    failure_reason: str,
    deps: ArenaBeatenNotificationDeps,
) -> dict[str, int]:
    async def _unexpected_send() -> None:
        raise RuntimeError("skipped Arena notification must not be sent")

    await deliver_telegram_once(
        deps.session_local,
        attempt=beaten_delivery_attempt(
            notification=notification,
            telegram_user_id=None,
        ),
        send=_unexpected_send,
        skip=TelegramDeliverySkip(
            failure_code=failure_code,
            failure_reason=failure_reason,
        ),
    )
    return {"sent_total": 0, "failed_total": 0, "skipped_total": 1}


def _result_for_delivery_outcome(outcome: TelegramDeliveryOutcome) -> dict[str, int]:
    if outcome.status == "SENT":
        if outcome.attempted:
            return {"sent_total": 1, "failed_total": 0, "skipped_total": 0}
        return {"sent_total": 0, "failed_total": 0, "skipped_total": 1}
    if outcome.status == "SKIPPED":
        return {"sent_total": 0, "failed_total": 0, "skipped_total": 1}
    return {"sent_total": 0, "failed_total": 1, "skipped_total": 0}


__all__ = [
    "ArenaBeatenNotificationDeps",
    "send_arena_beaten_notification_with_bot",
]
