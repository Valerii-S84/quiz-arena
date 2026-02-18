from __future__ import annotations

import pytest

from app.game.modes.rules import is_mode_allowed, is_zero_cost_source


@pytest.mark.parametrize(
    ("mode_code", "premium_active", "has_mode_access", "expected"),
    [
        ("QUICK_MIX_A1A2", False, False, True),
        ("ARTIKEL_SPRINT", False, False, True),
        ("CASES_PRACTICE", False, False, False),
        ("CASES_PRACTICE", False, True, True),
        ("CASES_PRACTICE", True, False, True),
    ],
)
def test_is_mode_allowed(
    mode_code: str,
    premium_active: bool,
    has_mode_access: bool,
    expected: bool,
) -> None:
    assert is_mode_allowed(
        mode_code=mode_code,
        premium_active=premium_active,
        has_mode_access=has_mode_access,
    ) is expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("DAILY_CHALLENGE", True),
        ("FRIEND_CHALLENGE", True),
        ("TOURNAMENT", True),
        ("MENU", False),
    ],
)
def test_is_zero_cost_source(source: str, expected: bool) -> None:
    assert is_zero_cost_source(source) is expected
