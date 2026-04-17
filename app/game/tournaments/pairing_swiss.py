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


def _build_pairs_backtracking(
    *,
    participants: list[SwissParticipant],
    previous_pairs: set[frozenset[int]],
) -> list[SwissPair]:
    user_ids = tuple(participant.user_id for participant in participants)

    @lru_cache(maxsize=None)
    def _search(
        remaining_ids: tuple[int, ...],
        *,
        allow_rematch: bool,
    ) -> tuple[tuple[int, int], ...] | None:
        if not remaining_ids:
            return ()

        user_a = remaining_ids[0]
        tail = remaining_ids[1:]
        candidate_ids = [
            candidate_id
            for candidate_id in tail
            if allow_rematch or _pair_key(user_a=user_a, user_b=candidate_id) not in previous_pairs
        ]
        if not candidate_ids:
            return None

        for candidate_id in candidate_ids:
            next_remaining = tuple(user_id for user_id in tail if user_id != candidate_id)
            nested = _search(next_remaining, allow_rematch=allow_rematch)
            if nested is None:
                continue
            return ((user_a, candidate_id),) + nested
        return None

    pairs = _search(user_ids, allow_rematch=False)
    if pairs is None:
        pairs = _search(user_ids, allow_rematch=True)
    if pairs is None:
        return []

    return [SwissPair(user_a=user_a, user_b=user_b) for user_a, user_b in pairs]


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

    pairs.extend(
        _build_pairs_backtracking(
            participants=remaining,
            previous_pairs=previous_pairs,
        )
    )

    if bye_pair is not None:
        pairs.append(bye_pair)

    return pairs
