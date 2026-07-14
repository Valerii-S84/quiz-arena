from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.services.telegram_delivery import SKIP_CODE_DUPLICATE, TelegramDeliveryTarget


@dataclass(frozen=True, slots=True)
class DailyCupRegistrationPushRun:
    bot: Any
    logger: Any
    flow: str
    task_name: str
    text: str
    tournament_id_text: str
    happened_at: datetime
    sent_event_type: str


@dataclass(frozen=True, slots=True)
class DailyCupRegistrationPushOperations:
    prepare_delivery: Any
    begin_dispatch: Any
    mark_failed: Any
    record_sent: Any
    build_keyboard: Any


async def process_registration_push_target(
    *,
    run: DailyCupRegistrationPushRun,
    user_id: int,
    telegram_user_id: int,
    already_pushed_user_ids: set[int],
    send_once: Any,
    record_skipped: Any,
    target_factory: Any,
) -> tuple[int, int]:
    target = target_factory(
        flow=run.flow,
        task_name=run.task_name,
        tournament_id_text=run.tournament_id_text,
        user_id=user_id,
        telegram_user_id=telegram_user_id,
    )
    if user_id in already_pushed_user_ids:
        await record_skipped(
            target=target,
            happened_at=run.happened_at,
            failure_code=SKIP_CODE_DUPLICATE,
            failure_reason="daily cup analytics sent event already exists",
        )
        return 0, 1
    sent = await send_once(run=run, target=target, user_id=user_id)
    return (1, 0) if sent else (0, 1)


async def send_daily_cup_registration_push_once(
    *,
    run: DailyCupRegistrationPushRun,
    target: TelegramDeliveryTarget,
    user_id: int,
    operations: DailyCupRegistrationPushOperations,
) -> bool:
    keyboard = operations.build_keyboard(tournament_id=run.tournament_id_text)
    delivery = await operations.prepare_delivery(target=target, happened_at=run.happened_at)
    if not delivery.should_send:
        return False

    await operations.begin_dispatch(delivery, happened_at=run.happened_at)
    try:
        await run.bot.send_message(
            chat_id=target.chat_id,
            text=run.text,
            reply_markup=keyboard,
        )
    except Exception as exc:
        await operations.mark_failed(
            idempotency_key=target.idempotency_key,
            happened_at=run.happened_at,
            exc=exc,
        )
        run.logger.warning(
            "daily_cup_registration_push_send_failed",
            event_type=run.sent_event_type,
            tournament_id=run.tournament_id_text,
            user_id=user_id,
            error_type=type(exc).__name__,
        )
        return False
    await operations.record_sent(
        target=target,
        user_id=user_id,
        event_type=run.sent_event_type,
        tournament_id=run.tournament_id_text,
        happened_at=run.happened_at,
    )
    return True


__all__ = [
    "DailyCupRegistrationPushOperations",
    "DailyCupRegistrationPushRun",
    "process_registration_push_target",
    "send_daily_cup_registration_push_once",
]
