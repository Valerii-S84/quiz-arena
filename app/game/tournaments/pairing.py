from __future__ import annotations

from app.game.tournaments.types import SwissPair, SwissParticipant


def _participant_sort_key(participant: SwissParticipant) -> tuple[object, ...]:
    return (
        -participant.score,
        -participant.tie_break,
        participant.joined_at,
        participant.user_id,
    )


def _pair_key(*, user_a: int, user_b: int) -> frozenset[int]:
    return frozenset((user_a, user_b))


def _pick_opponent_index(
    *,
    user_id: int,
    candidates: list[SwissParticipant],
    previous_pairs: set[frozenset[int]],
) -> int:
    for index, candidate in enumerate(candidates):
        if _pair_key(user_a=user_id, user_b=candidate.user_id) not in previous_pairs:
            return index
    return 0


def build_swiss_pairs(
    *,
    participants: list[SwissParticipant],
    previous_pairs: set[frozenset[int]],
) -> list[SwissPair]:
    ordered = sorted(participants, key=_participant_sort_key)
    remaining = list(ordered)
    pairs: list[SwissPair] = []

    while remaining:
        participant = remaining.pop(0)
        if not remaining:
            pairs.append(SwissPair(user_a=participant.user_id, user_b=None))
            break

        opponent_index = _pick_opponent_index(
            user_id=participant.user_id,
            candidates=remaining,
            previous_pairs=previous_pairs,
        )
        opponent = remaining.pop(opponent_index)
        pairs.append(SwissPair(user_a=participant.user_id, user_b=opponent.user_id))

    return pairs
