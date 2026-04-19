from __future__ import annotations

from functools import lru_cache

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


def _candidate_ids(
    *,
    tail: tuple[int, ...],
    user_a: int,
    previous_pairs: frozenset[frozenset[int]],
    allow_rematch: bool,
) -> tuple[int, ...]:
    return tuple(
        candidate_id
        for candidate_id in tail
        if allow_rematch or _pair_key(user_a=user_a, user_b=candidate_id) not in previous_pairs
    )


@lru_cache(maxsize=None)
def _search_pairs(
    remaining_ids: tuple[int, ...],
    previous_pairs: frozenset[frozenset[int]],
    allow_rematch: bool,
) -> tuple[tuple[int, int], ...] | None:
    if not remaining_ids:
        return ()

    user_a = remaining_ids[0]
    tail = remaining_ids[1:]
    for candidate_id in _candidate_ids(
        tail=tail,
        user_a=user_a,
        previous_pairs=previous_pairs,
        allow_rematch=allow_rematch,
    ):
        next_remaining = tuple(user_id for user_id in tail if user_id != candidate_id)
        nested_pairs = _search_pairs(next_remaining, previous_pairs, allow_rematch)
        if nested_pairs is not None:
            return ((user_a, candidate_id),) + nested_pairs
    return None


def _resolve_pairs(
    *,
    user_ids: tuple[int, ...],
    previous_pairs: set[frozenset[int]],
) -> tuple[tuple[int, int], ...] | None:
    previous_pairs_key = frozenset(previous_pairs)
    pairs = _search_pairs(user_ids, previous_pairs_key, False)
    if pairs is not None:
        return pairs
    return _search_pairs(user_ids, previous_pairs_key, True)


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
    bye_pair: SwissPair | None = None

    if len(remaining) % 2 == 1:
        bye_participant = _pick_bye_participant(
            participants=remaining,
            bye_history=bye_history or set(),
        )
        remaining = [participant for participant in remaining if participant != bye_participant]
        bye_pair = SwissPair(user_a=bye_participant.user_id, user_b=None)

    resolved_pairs = _resolve_pairs(
        user_ids=tuple(participant.user_id for participant in remaining),
        previous_pairs=previous_pairs,
    )
    pairs = (
        []
        if resolved_pairs is None
        else [SwissPair(user_a=user_a, user_b=user_b) for user_a, user_b in resolved_pairs]
    )
    if bye_pair is not None:
        pairs.append(bye_pair)
    return pairs
