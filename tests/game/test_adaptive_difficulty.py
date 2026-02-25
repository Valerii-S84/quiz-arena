from app.game.sessions.service import GameSessionService
from app.game.sessions.service.progression import get_allowed_levels, select_level_weighted


def test_get_allowed_levels_without_mix_contains_only_current() -> None:
    assert get_allowed_levels("A1", 0) == ("A1",)


def test_get_allowed_levels_with_mix_contains_current_and_next() -> None:
    assert get_allowed_levels("A1", 1) == ("A1", "A2")
    assert get_allowed_levels("A2", 3) == ("A2", "B1")


def test_select_level_weighted_stays_on_current_when_mix_disabled() -> None:
    assert select_level_weighted("A1", 0, selection_seed="seed-1") == "A1"


def test_select_level_weighted_never_goes_above_next_level() -> None:
    level = select_level_weighted("A2", 3, selection_seed="seed-2")
    assert level in ("A2", "B1")


def test_select_level_weighted_keeps_top_level_stable() -> None:
    assert select_level_weighted("B2", 3, selection_seed="seed-3") == "B2"


def test_artikel_sprint_default_start_level_is_a1() -> None:
    assert GameSessionService._clamp_level_for_mode(mode_code="ARTIKEL_SPRINT", level=None) == "A1"
