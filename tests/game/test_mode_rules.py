from __future__ import annotations

import pytest

from app.game.modes.rules import is_zero_cost_source, requires_duel_limit_gate


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("ARENA_DUEL", True),
        ("DAILY_CHALLENGE", True),
        ("FRIEND_CHALLENGE", True),
        ("TOURNAMENT", True),
        ("MENU", False),
    ],
)
def test_is_zero_cost_source(source: str, expected: bool) -> None:
    assert is_zero_cost_source(source) is expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("ARENA_DUEL", True),
        ("FRIEND_CHALLENGE", False),
        ("MENU", False),
    ],
)
def test_requires_duel_limit_gate(source: str, expected: bool) -> None:
    assert requires_duel_limit_gate(source) is expected
