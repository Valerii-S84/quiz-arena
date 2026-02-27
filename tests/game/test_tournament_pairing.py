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
