from __future__ import annotations

from app.game.tournaments import settlement


def test_score_deltas_cover_bye_and_user_b_win() -> None:
    assert settlement._score_deltas_for_match(
        match_status="COMPLETED",
        winner_id=11,
        user_a=11,
        user_b=None,
        score_a=5,
        score_b=0,
    ) == [(11, settlement.Decimal("1"), settlement.Decimal("5"))]
    assert settlement._score_deltas_for_match(
        match_status="COMPLETED",
        winner_id=22,
        user_a=11,
        user_b=22,
        score_a=2,
        score_b=5,
    ) == [
        (11, settlement.Decimal("0"), settlement.Decimal("2")),
        (22, settlement.Decimal("1"), settlement.Decimal("5")),
    ]
