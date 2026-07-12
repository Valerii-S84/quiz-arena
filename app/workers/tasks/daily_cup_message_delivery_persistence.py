from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.db.repo.production_reliability_repo import TelegramDeliveryAttemptsRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.session import SessionLocal
from app.services.telegram_delivery import TelegramDeliveryTarget
from app.workers.tasks.tournaments_messaging_persistence import persist_standings_message_ids


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
    async with SessionLocal.begin() as session:
        await persist_standings_message_ids(
            session=session,
            parsed_tournament_id=tournament_id,
            participants_repo=TournamentParticipantsRepo,
            new_message_ids={} if replace_existing else {user_id: message_id},
            replaced_message_ids={user_id: message_id} if replace_existing else {},
        )
        sent = await TelegramDeliveryAttemptsRepo.mark_sent(
            session,
            idempotency_key=target.idempotency_key,
            sent_at=happened_at,
        )
        if sent != 1:
            raise RuntimeError("daily cup delivery terminal lease was lost")
    return message_id


__all__ = ["persist_daily_cup_sent_message"]
