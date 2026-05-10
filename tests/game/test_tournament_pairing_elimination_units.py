from __future__ import annotations

import pytest

from app.game.tournaments import pairing_elimination as elimination


def test_elimination_helpers_validate_inputs_and_defaults() -> None:
    assert elimination._to_int(True, default=9) == 1
    assert elimination._to_int("12", default=9) == 12
    assert elimination._to_int("bad", default=9) == 9
    assert elimination._to_int(object(), default=9) == 9
    assert elimination._next_power_of_two(0) == 1
    assert elimination._next_power_of_two(9) == 16
    assert elimination._evenly_spaced_indices(total=8, count=0) == []
    assert elimination._evenly_spaced_indices(total=8, count=3) == [0, 2, 5]

    with pytest.raises(ValueError):
        elimination._evenly_spaced_indices(total=2, count=3)
    with pytest.raises(ValueError):
        elimination.distribute_byes([1, 2], bracket_size=4, bye_count=1)
    with pytest.raises(ValueError):
        elimination.create_elimination_bracket([1], tournament_id=1)
    with pytest.raises(ValueError):
        elimination.get_winner_bracket_slot(-1, {"size": 4})
    with pytest.raises(ValueError):
        elimination.get_winner_bracket_slot(4, {"size": 4})


def test_get_next_opponent_handles_malformed_slots() -> None:
    assert elimination.get_next_opponent(0, {}) is None
    assert elimination.get_next_opponent(0, {"slots": []}) is None
    assert elimination.get_next_opponent(0, {"slots": ["bad", "bad"]}) is None
    assert elimination.get_next_opponent(0, {"slots": [{}, {"player_id": None}]}) is None
    assert elimination.get_next_opponent(0, {"slots": [{}, {"player_id": "bad"}]}) is None
    assert elimination.get_next_opponent(0, {"slots": [{}, {"player_id": "22"}]}) == 22
