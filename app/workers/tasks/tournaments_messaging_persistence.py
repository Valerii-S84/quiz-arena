from __future__ import annotations

from typing import Any
from uuid import UUID


async def persist_standings_message_ids(
    *,
    session: Any,
    parsed_tournament_id: UUID,
    participants_repo: Any,
    new_message_ids: dict[int, int],
    replaced_message_ids: dict[int, int],
) -> None:
    for user_id, message_id in new_message_ids.items():
        await participants_repo.set_standings_message_id_if_missing(
            session,
            tournament_id=parsed_tournament_id,
            user_id=user_id,
            message_id=message_id,
        )
    for user_id, message_id in replaced_message_ids.items():
        await participants_repo.set_standings_message_id(
            session,
            tournament_id=parsed_tournament_id,
            user_id=user_id,
            message_id=message_id,
        )


__all__ = ["persist_standings_message_ids"]
