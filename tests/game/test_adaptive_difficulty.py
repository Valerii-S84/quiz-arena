from app.game.sessions.service import GameSessionService


def test_next_preferred_level_moves_up_when_correct() -> None:
    assert GameSessionService._next_preferred_level(question_level="A1", is_correct=True) == "A2"
    assert GameSessionService._next_preferred_level(question_level="B2", is_correct=True) == "C1"


def test_next_preferred_level_keeps_level_when_incorrect() -> None:
    assert GameSessionService._next_preferred_level(question_level="B1", is_correct=False) == "B1"


def test_next_preferred_level_stays_at_max_level() -> None:
    assert GameSessionService._next_preferred_level(question_level="C2", is_correct=True) == "C2"


def test_next_preferred_level_returns_none_for_unknown() -> None:
    assert GameSessionService._next_preferred_level(question_level="X1", is_correct=True) is None


def test_artikel_sprint_level_clamped_to_b2() -> None:
    assert (
        GameSessionService._next_preferred_level(
            question_level="B2",
            is_correct=True,
            mode_code="ARTIKEL_SPRINT",
        )
        == "B2"
    )


def test_artikel_sprint_default_start_level_is_a1() -> None:
    assert GameSessionService._clamp_level_for_mode(mode_code="ARTIKEL_SPRINT", level=None) == "A1"
