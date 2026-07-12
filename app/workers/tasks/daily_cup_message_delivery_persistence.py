from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.services.telegram_delivery import TelegramDeliveryTarget, mark_telegram_delivery_sent
from app.workers.tasks.daily_cup_core import persist_daily_cup_standings_message_ids


async def persist_daily_cup_sent_message(
    target: TelegramDeliveryTarget,
    tournament_id: UUID,
    user_id: int,
    message: Any,
    happened_at: datetime,
    *,
    replace_existing: bool = False,
) -> int:
    message_id = int(message.message_id)
    await persist_daily_cup_standings_message_ids(
        tournament_id=tournament_id,
        new_message_ids={} if replace_existing else {user_id: message_id},
        replaced_message_ids={user_id: message_id} if replace_existing else {},
    )
    await mark_telegram_delivery_sent(
        idempotency_key=target.idempotency_key,
        happened_at=happened_at,
    )
    return message_id


__all__ = ["persist_daily_cup_sent_message"]
