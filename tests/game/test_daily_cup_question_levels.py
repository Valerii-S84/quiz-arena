from app.game.tournaments.daily_cup_question_levels import resolve_daily_cup_preferred_levels


def test_round_1_uses_only_a1_for_all_7_questions() -> None:
    assert resolve_daily_cup_preferred_levels(round_no=1, duel_rounds=7) == (
        "A1",
        "A1",
        "A1",
        "A1",
        "A1",
        "A1",
        "A1",
    )


def test_round_2_uses_only_a2() -> None:
    assert resolve_daily_cup_preferred_levels(round_no=2, duel_rounds=7) == (
        "A2",
        "A2",
        "A2",
        "A2",
        "A2",
        "A2",
        "A2",
    )


def test_round_3_uses_four_a2_and_three_b1() -> None:
    assert resolve_daily_cup_preferred_levels(round_no=3, duel_rounds=7) == (
        "A2",
        "A2",
        "A2",
        "A2",
        "B1",
        "B1",
        "B1",
    )


def test_round_4_uses_three_b1_and_four_b2() -> None:
    assert resolve_daily_cup_preferred_levels(round_no=4, duel_rounds=7) == (
        "B1",
        "B1",
        "B1",
        "B2",
        "B2",
        "B2",
        "B2",
    )


def test_non_quick_5_returns_none() -> None:
    assert resolve_daily_cup_preferred_levels(round_no=1, duel_rounds=5) is None
