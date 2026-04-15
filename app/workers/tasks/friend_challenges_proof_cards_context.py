from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class FriendChallengeProofCardRecipient:
    role: str
    user_id: int
    chat_id: int
    cached_file_id: str | None


@dataclass(frozen=True, slots=True)
class FriendChallengeProofCardsContext:
    parsed_challenge_id: UUID
    challenge_id: str
    status: str
    creator_score: int
    opponent_score: int
    total_rounds: int
    completed_at: Any
    creator_name: str
    opponent_name: str
    recipients: list[FriendChallengeProofCardRecipient]


async def load_friend_challenge_proof_cards_context(
    *,
    session: Any,
    parsed_challenge_id: UUID,
    requested_user_id: int | None,
    challenges_repo: Any,
    users_repo: Any,
    final_statuses: set[str] | frozenset[str],
    resolve_user_label_fn: Any,
) -> FriendChallengeProofCardsContext | None:
    challenge = await challenges_repo.get_by_id_for_update(session, parsed_challenge_id)
    if challenge is None or challenge.status not in final_statuses:
        return None

    creator = await users_repo.get_by_id(session, challenge.creator_user_id)
    opponent = (
        await users_repo.get_by_id(session, int(challenge.opponent_user_id))
        if challenge.opponent_user_id is not None
        else None
    )
    creator_user_id = int(challenge.creator_user_id)
    opponent_user_id = (
        int(challenge.opponent_user_id) if challenge.opponent_user_id is not None else None
    )
    recipients: list[FriendChallengeProofCardRecipient] = []
    creator_chat = int(creator.telegram_user_id) if creator is not None else None
    if creator_chat is not None and (
        requested_user_id is None or requested_user_id == creator_user_id
    ):
        recipients.append(
            FriendChallengeProofCardRecipient(
                role="creator",
                user_id=creator_user_id,
                chat_id=creator_chat,
                cached_file_id=challenge.creator_proof_card_file_id,
            )
        )
    opponent_chat = int(opponent.telegram_user_id) if opponent is not None else None
    if (
        opponent_chat is not None
        and opponent_user_id is not None
        and (requested_user_id is None or requested_user_id == opponent_user_id)
    ):
        recipients.append(
            FriendChallengeProofCardRecipient(
                role="opponent",
                user_id=opponent_user_id,
                chat_id=opponent_chat,
                cached_file_id=challenge.opponent_proof_card_file_id,
            )
        )

    return FriendChallengeProofCardsContext(
        parsed_challenge_id=parsed_challenge_id,
        challenge_id=str(challenge.id),
        status=str(challenge.status),
        creator_score=int(challenge.creator_score),
        opponent_score=int(challenge.opponent_score),
        total_rounds=int(challenge.total_rounds),
        completed_at=challenge.completed_at,
        creator_name=resolve_user_label_fn(user=creator, fallback="Spieler 1"),
        opponent_name=resolve_user_label_fn(user=opponent, fallback="Spieler 2"),
        recipients=recipients,
    )


__all__ = [
    "FriendChallengeProofCardRecipient",
    "FriendChallengeProofCardsContext",
    "load_friend_challenge_proof_cards_context",
]
