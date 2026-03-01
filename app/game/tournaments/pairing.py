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


def _pick_bye_participant(
    *,
    participants: list[SwissParticipant],
    bye_history: set[int],
) -> SwissParticipant:
    lowest_first = sorted(
        participants,
        key=lambda participant: (
            participant.score,
            participant.tie_break,
            participant.joined_at,
            participant.user_id,
        ),
    )
    for participant in lowest_first:
        if participant.user_id not in bye_history:
            return participant
    return lowest_first[0]


def build_swiss_pairs(
    *,
    participants: list[SwissParticipant],
    previous_pairs: set[frozenset[int]],
    bye_history: set[int] | None = None,
) -> list[SwissPair]:
    ordered = sorted(participants, key=_participant_sort_key)
    remaining = list(ordered)
    pairs: list[SwissPair] = []
    resolved_bye_history = bye_history or set()
    bye_pair: SwissPair | None = None

    if len(remaining) % 2 == 1:
        bye_participant = _pick_bye_participant(
            participants=remaining,
            bye_history=resolved_bye_history,
        )
        remaining = [
            participant
            for participant in remaining
            if participant.user_id != bye_participant.user_id
        ]
        bye_pair = SwissPair(user_a=bye_participant.user_id, user_b=None)

    while remaining:
        participant = remaining.pop(0)

        opponent_index = _pick_opponent_index(
            user_id=participant.user_id,
            candidates=remaining,
            previous_pairs=previous_pairs,
        )
        opponent = remaining.pop(opponent_index)
        pairs.append(SwissPair(user_a=participant.user_id, user_b=opponent.user_id))

    if bye_pair is not None:
        pairs.append(bye_pair)

    return pairs
