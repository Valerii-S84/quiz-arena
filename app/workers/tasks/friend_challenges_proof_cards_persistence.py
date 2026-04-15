from __future__ import annotations

from typing import Any
from uuid import UUID


async def persist_friend_challenge_proof_card_file_ids(
    *,
    session: Any,
    parsed_challenge_id: UUID,
    challenges_repo: Any,
    new_creator_file_id: str | None,
    new_opponent_file_id: str | None,
) -> None:
    challenge_row = await challenges_repo.get_by_id_for_update(session, parsed_challenge_id)
    if challenge_row is None:
        return
    if new_creator_file_id is not None and not challenge_row.creator_proof_card_file_id:
        challenge_row.creator_proof_card_file_id = new_creator_file_id
    if new_opponent_file_id is not None and not challenge_row.opponent_proof_card_file_id:
        challenge_row.opponent_proof_card_file_id = new_opponent_file_id


__all__ = ["persist_friend_challenge_proof_card_file_ids"]
