from app.game.tournaments.daily_cup_question_levels import resolve_daily_cup_preferred_levels


def test_round_1_uses_a1_a1_a1_a2_a2() -> None:
    assert resolve_daily_cup_preferred_levels(round_no=1, duel_rounds=5) == (
        "A1",
        "A1",
        "A1",
        "A2",
        "A2",
    )


def test_round_2_uses_only_a2() -> None:
    assert resolve_daily_cup_preferred_levels(round_no=2, duel_rounds=5) == (
        "A2",
        "A2",
        "A2",
        "A2",
        "A2",
    )


def test_round_3_uses_a2_b1_b1_b1_b2() -> None:
    assert resolve_daily_cup_preferred_levels(round_no=3, duel_rounds=5) == (
        "A2",
        "B1",
        "B1",
        "B1",
        "B2",
    )


def test_non_quick_5_returns_none() -> None:
    assert resolve_daily_cup_preferred_levels(round_no=1, duel_rounds=12) is None
