from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.game.tournaments.pairing import build_swiss_pairs
from app.game.tournaments.types import SwissParticipant

UTC = timezone.utc


def _participant(
    *,
    user_id: int,
    score: str,
    tie_break: str,
    joined_offset_minutes: int,
) -> SwissParticipant:
    return SwissParticipant(
        user_id=user_id,
        score=Decimal(score),
        tie_break=Decimal(tie_break),
        joined_at=datetime(2026, 2, 27, 12, joined_offset_minutes, tzinfo=UTC),
    )


def test_build_swiss_pairs_avoids_rematch_when_possible() -> None:
    participants = [
        _participant(user_id=1, score="2", tie_break="1", joined_offset_minutes=1),
        _participant(user_id=2, score="2", tie_break="0.5", joined_offset_minutes=2),
        _participant(user_id=3, score="1", tie_break="1", joined_offset_minutes=3),
        _participant(user_id=4, score="1", tie_break="0.5", joined_offset_minutes=4),
    ]
    pairs = build_swiss_pairs(
        participants=participants,
        previous_pairs={frozenset((1, 2))},
    )
    pair_sets = {
        frozenset((pair.user_a, int(pair.user_b))) for pair in pairs if pair.user_b is not None
    }
    assert frozenset((1, 3)) in pair_sets
    assert frozenset((2, 4)) in pair_sets


def test_build_swiss_pairs_returns_bye_for_odd_participants() -> None:
    participants = [
        _participant(user_id=10, score="1", tie_break="0", joined_offset_minutes=1),
        _participant(user_id=11, score="0", tie_break="0", joined_offset_minutes=2),
        _participant(user_id=12, score="0", tie_break="0", joined_offset_minutes=3),
    ]
    pairs = build_swiss_pairs(participants=participants, previous_pairs=set())
    bye_pairs = [pair for pair in pairs if pair.user_b is None]
    assert len(bye_pairs) == 1
    assert len(pairs) == 2


def test_two_player_tournament_pairings() -> None:
    participants = [
        _participant(user_id=1, score="1", tie_break="0", joined_offset_minutes=1),
        _participant(user_id=2, score="1", tie_break="0", joined_offset_minutes=2),
    ]
    pairs = build_swiss_pairs(
        participants=participants,
        previous_pairs={frozenset((1, 2))},
    )
    assert len(pairs) == 1
    assert pairs[0].user_a in {1, 2}
    assert pairs[0].user_b in {1, 2}
    assert frozenset((pairs[0].user_a, int(pairs[0].user_b))) == frozenset((1, 2))


def test_eight_player_no_rematch() -> None:
    participants = [
        _participant(user_id=user_id, score="0", tie_break="0", joined_offset_minutes=user_id)
        for user_id in range(1, 9)
    ]
    by_user_id = {participant.user_id: participant for participant in participants}
    history: set[frozenset[int]] = set()

    for round_no in range(1, 4):
        round_pairs = build_swiss_pairs(
            participants=list(by_user_id.values()),
            previous_pairs=history,
        )
        for pair in round_pairs:
            assert pair.user_b is not None
            pair_key = frozenset((pair.user_a, int(pair.user_b)))
            assert pair_key not in history, f"Rematch im Runde {round_no}: {pair_key}"
            history.add(pair_key)
            by_user_id[pair.user_a].score += Decimal("1")


def test_build_swiss_pairs_does_not_repeat_bye_when_alternative_exists() -> None:
    participants = [
        _participant(user_id=10, score="2", tie_break="1", joined_offset_minutes=1),
        _participant(user_id=11, score="1", tie_break="0", joined_offset_minutes=2),
        _participant(user_id=12, score="1", tie_break="0", joined_offset_minutes=3),
    ]
    round_pairs = build_swiss_pairs(
        participants=participants,
        previous_pairs=set(),
        bye_history={11},
    )
    bye_pair = next(pair for pair in round_pairs if pair.user_b is None)
    assert bye_pair.user_a != 11
