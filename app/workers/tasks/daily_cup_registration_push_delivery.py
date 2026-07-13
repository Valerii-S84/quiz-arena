from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.services.telegram_delivery import TelegramDeliveryTarget


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


async def send_daily_cup_registration_push_once(
    *,
    run: DailyCupRegistrationPushRun,
    target: TelegramDeliveryTarget,
    user_id: int,
    operations: DailyCupRegistrationPushOperations,
) -> bool:
    delivery = await operations.prepare_delivery(target=target, happened_at=run.happened_at)
    if not delivery.should_send:
        return False

    await operations.begin_dispatch(delivery, happened_at=run.happened_at)
    try:
        await run.bot.send_message(
            chat_id=target.chat_id,
            text=run.text,
            reply_markup=operations.build_keyboard(tournament_id=run.tournament_id_text),
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
    "send_daily_cup_registration_push_once",
]
