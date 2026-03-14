from __future__ import annotations

from app.game.sessions.service import levels


def test_normalize_level_handles_none_blank_and_casefolding() -> None:
    assert levels._normalize_level(None) is None
    assert levels._normalize_level("   ") is None
    assert levels._normalize_level(" a2 ") == "A2"


def test_is_persistent_adaptive_mode_matches_mode_config() -> None:
    assert levels._is_persistent_adaptive_mode(mode_code="ARTIKEL_SPRINT") is True
    assert levels._is_persistent_adaptive_mode(mode_code="UNKNOWN") is False


def test_clamp_level_for_mode_respects_unknown_mode_and_bounds() -> None:
    assert levels._clamp_level_for_mode(mode_code="UNKNOWN", level=" a2 ") == "A2"
    assert levels._clamp_level_for_mode(mode_code="ARTIKEL_SPRINT", level=None) == "A1"
    assert levels._clamp_level_for_mode(mode_code="ARTIKEL_SPRINT", level="Z9") == "A1"
    assert levels._clamp_level_for_mode(mode_code="ARTIKEL_SPRINT", level="A1") == "A1"
    assert levels._clamp_level_for_mode(mode_code="ARTIKEL_SPRINT", level="C2") == "B2"


def test_next_preferred_level_handles_invalid_incorrect_and_correct_answers() -> None:
    assert levels._next_preferred_level(question_level=None, is_correct=True) is None
    assert levels._next_preferred_level(question_level="Z9", is_correct=True) is None
    assert levels._next_preferred_level(question_level="A2", is_correct=False) == "A2"
    assert levels._next_preferred_level(question_level="A2", is_correct=True) == "B1"
    assert levels._next_preferred_level(question_level="C2", is_correct=True) == "C2"


def test_next_preferred_level_clamps_to_mode_bounds() -> None:
    assert (
        levels._next_preferred_level(
            question_level="B2",
            is_correct=True,
            mode_code="ARTIKEL_SPRINT",
        )
        == "B2"
    )
    assert (
        levels._next_preferred_level(
            question_level="A1",
            is_correct=True,
            mode_code="ARTIKEL_SPRINT",
        )
        == "A2"
    )


def test_friend_challenge_level_for_round_handles_bounds() -> None:
    assert levels._friend_challenge_level_for_round(round_number=0) is None
    assert levels._friend_challenge_level_for_round(round_number=1) == "A1"
    assert levels._friend_challenge_level_for_round(round_number=4) == "A2"
    assert levels._friend_challenge_level_for_round(round_number=99) == "B1"
