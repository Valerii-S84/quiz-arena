from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.analytics_events import BERLIN_TIMEZONE
from app.game.arena_duels.constants import ARENA_BEATEN_NOTIFICATION_EVENT
from app.game.arena_duels.types import ArenaBeatenNotification
from app.services.telegram_delivery import (
    SKIP_CODE_DUPLICATE,
    TelegramDeliveryTarget,
    begin_telegram_delivery_dispatch,
    build_delivery_idempotency_key,
    mark_telegram_delivery_failed,
    mark_telegram_delivery_sent,
    prepare_telegram_delivery,
    record_telegram_delivery_skipped,
)
from app.workers.tasks.arena_duels_notification_content import (
    build_arena_beaten_notification_keyboard,
    build_notification_text,
    classify_beaten_notification_action_mode,
    format_user_label,
)
from app.workers.tasks.arena_duels_notification_payload import notification_payload


@dataclass(frozen=True, slots=True)
class ArenaBeatenNotificationDeps:
    session_local: Any
    analytics_repo: Any
    users_repo: Any


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
            await record_telegram_delivery_skipped(
                target=_beaten_delivery_target(
                    notification=notification,
                    telegram_user_id=None,
                ),
                happened_at=happened_at,
                failure_code=SKIP_CODE_DUPLICATE,
                failure_reason="beaten notification analytics event already exists",
                session_local=deps.session_local,
            )
            return {"sent_total": 0, "failed_total": 0, "skipped_total": 1}

        previous_user, new_best_user = await _load_notification_users(session, notification, deps)
        if previous_user is None:
            await record_telegram_delivery_skipped(
                target=_beaten_delivery_target(
                    notification=notification,
                    telegram_user_id=None,
                ),
                happened_at=happened_at,
                failure_code="MISSING_TARGET_USER",
                failure_reason="target user missing",
                session_local=deps.session_local,
            )
            return {"sent_total": 0, "failed_total": 0, "skipped_total": 1}

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
        )

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


async def _notification_already_sent(
    session,
    notification: ArenaBeatenNotification,
    payload: dict[str, object],
    deps: ArenaBeatenNotificationDeps,
) -> bool:
    await deps.analytics_repo.lock_arena_beaten_notification_event_key(
        session,
        event_type=ARENA_BEATEN_NOTIFICATION_EVENT,
        user_id=notification.previous_best_user_id,
        payload=payload,
    )
    return await deps.analytics_repo.has_arena_beaten_notification_event(
        session,
        event_type=ARENA_BEATEN_NOTIFICATION_EVENT,
        user_id=notification.previous_best_user_id,
        payload=payload,
    )


async def _load_notification_users(
    session,
    notification: ArenaBeatenNotification,
    deps: ArenaBeatenNotificationDeps,
):
    users = await deps.users_repo.list_by_ids(
        session,
        [notification.previous_best_user_id, notification.new_best_user_id],
    )
    users_by_id = {int(user.id): user for user in users}
    return (
        users_by_id.get(notification.previous_best_user_id),
        users_by_id.get(notification.new_best_user_id),
    )


async def _send_notification_message(
    bot,
    notification: ArenaBeatenNotification,
    previous_user,
    new_best_user,
) -> None:
    challenger_label = format_user_label(
        username=getattr(new_best_user, "username", None),
        first_name=getattr(new_best_user, "first_name", None),
        fallback=f"Spieler #{notification.new_best_user_id}",
    )
    await bot.send_message(
        chat_id=int(previous_user.telegram_user_id),
        text=build_notification_text(
            notification=notification,
            challenger_label=challenger_label,
        ),
        reply_markup=build_arena_beaten_notification_keyboard(
            source_attempt_id=str(notification.new_best_attempt_id),
            action_mode=classify_beaten_notification_action_mode(notification),
        ),
    )


def _beaten_delivery_target(
    *,
    notification: ArenaBeatenNotification,
    telegram_user_id: int | None,
) -> TelegramDeliveryTarget:
    correlation_id = ":".join(
        (
            str(notification.arena_duel_id),
            str(notification.previous_best_attempt_id),
            str(notification.new_best_attempt_id),
        )
    )
    target_id = str(notification.previous_best_user_id)
    return TelegramDeliveryTarget(
        flow="arena_beaten_notification",
        task_name="arena_duels.send_arena_beaten_notification_task",
        correlation_id=correlation_id,
        target_type="user",
        target_id=target_id,
        idempotency_key=build_delivery_idempotency_key(
            flow="arena_beaten_notification",
            correlation_id=correlation_id,
            target_type="user",
            target_id=target_id,
        ),
        telegram_user_id=telegram_user_id,
        chat_id=telegram_user_id,
        safe_context={
            "arena_duel_id": str(notification.arena_duel_id),
            "previous_best_user_id": notification.previous_best_user_id,
            "new_best_user_id": notification.new_best_user_id,
        },
    )
