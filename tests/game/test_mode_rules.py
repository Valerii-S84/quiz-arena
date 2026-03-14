from __future__ import annotations

import pytest

from app.game.modes.rules import is_zero_cost_source


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
