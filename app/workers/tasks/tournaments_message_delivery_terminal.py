from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.db.repo.telegram_delivery_attempts_repo import TelegramDeliveryAttemptsRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.session import SessionLocal
from app.workers.tasks.tournaments_messaging_delivery_targets import (
    SKIP_CODE_EDIT_REPLACED_BY_SEND,
    PrivateTournamentDeliveryTarget,
)


@dataclass(frozen=True, slots=True)
class PrivateTournamentStandingsFence:
    tournament_id: UUID
    user_id: int
    expected_message_id: int | None
    expected_status: str
    expected_round: int


async def persist_private_tournament_sent_message(
    target: PrivateTournamentDeliveryTarget,
    fence: PrivateTournamentStandingsFence,
    message: Any | int,
    happened_at: datetime,
    *,
    original_target: PrivateTournamentDeliveryTarget | None = None,
) -> int:
    del happened_at
    message_id = int(message if isinstance(message, int) else message.message_id)
    async with SessionLocal.begin() as session:
        persisted = await TournamentParticipantsRepo.compare_and_set_standings_message_id(
            session,
            tournament_id=fence.tournament_id,
            user_id=fence.user_id,
            expected_message_id=fence.expected_message_id,
            message_id=message_id,
            expected_status=fence.expected_status,
            expected_round=fence.expected_round,
        )
        if persisted != 1:
            raise RuntimeError("private tournament standings delivery fence was lost")
        sent = await TelegramDeliveryAttemptsRepo.mark_sent(
            session,
            idempotency_key=target.idempotency_key,
        )
        if not sent:
            raise RuntimeError("private tournament delivery terminal lease was lost")
        if original_target is not None:
            skipped = await TelegramDeliveryAttemptsRepo.mark_skipped(
                session,
                idempotency_key=original_target.idempotency_key,
                failure_code=SKIP_CODE_EDIT_REPLACED_BY_SEND,
                failure_reason="edit delivery replaced by fallback send",
            )
            if not skipped:
                raise RuntimeError("private tournament original edit lease was lost")
    return message_id


__all__ = ["PrivateTournamentStandingsFence", "persist_private_tournament_sent_message"]
