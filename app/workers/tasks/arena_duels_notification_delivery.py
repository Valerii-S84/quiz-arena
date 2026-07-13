from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.analytics_events import BERLIN_TIMEZONE
from app.game.arena_duels.constants import ARENA_BEATEN_NOTIFICATION_EVENT
from app.game.arena_duels.types import ArenaBeatenNotification
from app.services.telegram_delivery import (
    SKIP_CODE_DUPLICATE,
    begin_telegram_delivery_dispatch,
    mark_telegram_delivery_failed,
    mark_telegram_delivery_sent,
    prepare_telegram_delivery,
    record_telegram_delivery_skipped,
)
from app.workers.tasks import arena_duels_notification_content as notification_content
from app.workers.tasks import arena_duels_notification_delivery_target as delivery_target
from app.workers.tasks.arena_duels_notification_delivery_queries import ArenaBeatenNotificationDeps
from app.workers.tasks.arena_duels_notification_delivery_queries import (
    load_notification_users as _load_notification_users,
)
from app.workers.tasks.arena_duels_notification_delivery_queries import (
    notification_already_sent as _notification_already_sent,
)
from app.workers.tasks.arena_duels_notification_payload import notification_payload
from app.workers.tasks.arena_duels_notification_sender import _send_notification_message

TelegramDeliveryTarget = delivery_target.TelegramDeliveryTarget
build_delivery_idempotency_key = delivery_target.build_delivery_idempotency_key
_beaten_delivery_target = delivery_target._beaten_delivery_target
build_arena_beaten_notification_keyboard = (
    notification_content.build_arena_beaten_notification_keyboard
)
build_notification_text = notification_content.build_notification_text
classify_beaten_notification_action_mode = (
    notification_content.classify_beaten_notification_action_mode
)
format_user_label = notification_content.format_user_label


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
        if await _notification_already_sent(session, notification, payload, deps):
            return await _record_skipped_notification(
                notification=notification,
                happened_at=happened_at,
                failure_code=SKIP_CODE_DUPLICATE,
                failure_reason="beaten notification analytics event already exists",
                deps=deps,
            )

        previous_user, new_best_user = await _load_notification_users(session, notification, deps)
        if previous_user is None:
            return await _record_skipped_notification(
                notification=notification,
                happened_at=happened_at,
                failure_code="MISSING_TARGET_USER",
                failure_reason="target user missing",
                deps=deps,
            )

        delivery_outcome = await _deliver_notification(
            bot=bot,
            notification=notification,
            happened_at=happened_at,
            deps=deps,
            session=session,
            previous_user=previous_user,
            new_best_user=new_best_user,
        )
        if delivery_outcome is not None:
            return delivery_outcome

        await deps.analytics_repo.create_arena_beaten_notification_event_once(
            session,
            event_type=ARENA_BEATEN_NOTIFICATION_EVENT,
            source=source,
            user_id=notification.previous_best_user_id,
            local_date_berlin=local_date_berlin,
            payload=payload,
            happened_at=happened_at,
        )

    return {"sent_total": 1, "failed_total": 0, "skipped_total": 0}


async def _record_skipped_notification(
    *,
    notification: ArenaBeatenNotification,
    happened_at: datetime,
    failure_code: str,
    failure_reason: str,
    deps: ArenaBeatenNotificationDeps,
) -> dict[str, int]:
    await record_telegram_delivery_skipped(
        target=_beaten_delivery_target(
            notification=notification,
            telegram_user_id=None,
        ),
        happened_at=happened_at,
        failure_code=failure_code,
        failure_reason=failure_reason,
        session_local=deps.session_local,
    )
    return {"sent_total": 0, "failed_total": 0, "skipped_total": 1}


async def _deliver_notification(
    *,
    bot,
    notification: ArenaBeatenNotification,
    happened_at: datetime,
    deps: ArenaBeatenNotificationDeps,
    session,
    previous_user,
    new_best_user,
) -> dict[str, int] | None:
    target = _beaten_delivery_target(
        notification=notification,
        telegram_user_id=int(previous_user.telegram_user_id),
    )
    delivery = await prepare_telegram_delivery(
        target=target,
        happened_at=happened_at,
        session_local=deps.session_local,
    )
    if not delivery.should_send:
        return {"sent_total": 0, "failed_total": 0, "skipped_total": 1}
    await begin_telegram_delivery_dispatch(
        delivery,
        happened_at=happened_at,
        session_local=deps.session_local,
    )
    try:
        await _send_notification_message(bot, notification, previous_user, new_best_user)
    except Exception as exc:
        await mark_telegram_delivery_failed(
            idempotency_key=target.idempotency_key,
            happened_at=happened_at,
            exc=exc,
            session_local=deps.session_local,
        )
        return {"sent_total": 0, "failed_total": 1, "skipped_total": 0}
    await mark_telegram_delivery_sent(
        idempotency_key=target.idempotency_key,
        happened_at=happened_at,
        session_local=deps.session_local,
        session=session,
    )
    return None
