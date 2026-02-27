from __future__ import annotations


def enqueue_duel_proof_cards(*, challenge_id: str) -> None:
    from app.workers.tasks.friend_challenges_proof_cards import (
        enqueue_friend_challenge_proof_cards,
    )

    enqueue_friend_challenge_proof_cards(challenge_id=challenge_id)
