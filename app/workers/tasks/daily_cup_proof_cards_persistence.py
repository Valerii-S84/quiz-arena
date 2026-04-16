from __future__ import annotations

from typing import Any
from uuid import UUID


async def persist_daily_cup_proof_card_delivery(
    *,
    session: Any,
    parsed_tournament_id: UUID,
    participants_repo: Any,
    sent_user_ids: set[int],
    new_file_ids: dict[int, str],
) -> None:
    for current_user_id in sent_user_ids:
        await participants_repo.set_proof_card_sent(
            session,
            tournament_id=parsed_tournament_id,
            user_id=current_user_id,
        )
    for current_user_id, file_id in new_file_ids.items():
        await participants_repo.set_proof_card_file_id_if_missing(
            session,
            tournament_id=parsed_tournament_id,
            user_id=current_user_id,
            file_id=file_id,
        )


__all__ = ["persist_daily_cup_proof_card_delivery"]
