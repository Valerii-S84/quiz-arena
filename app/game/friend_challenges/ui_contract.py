from __future__ import annotations

from dataclasses import dataclass

FRIEND_CHALLENGE_LEVEL_SEQUENCE: tuple[str, ...] = (
    "A1",
    "A1",
    "A1",
    "A2",
    "A2",
    "A2",
    "A2",
    "A2",
    "A2",
    "B1",
    "B1",
    "B1",
)


@dataclass(slots=True)
class FriendSeriesScore:
    """Scoreboard payload used by bot rendering for best-of series duels."""

    my_wins: int
    opponent_wins: int
    game_no: int
    best_of: int

    @classmethod
    def from_tuple(cls, value: tuple[int, int, int, int]) -> FriendSeriesScore:
        """Builds the typed score view from service tuple output."""

        return cls(
            my_wins=value[0],
            opponent_wins=value[1],
            game_no=value[2],
            best_of=value[3],
        )
