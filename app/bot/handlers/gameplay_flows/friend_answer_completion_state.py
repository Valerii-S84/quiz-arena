from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError


@dataclass(frozen=True, slots=True)
class FriendSeriesContext:
    my_wins: int
    opponent_wins: int
    game_no: int
    best_of: int
    series_finished: bool
    show_next_series_game: bool
    champion_label: str


async def resolve_friend_series_context(
    *,
    challenge: Any,
    snapshot_user_id: int,
    opponent_label: str,
    now_utc: datetime,
    session_local: Any,
    game_session_service: Any,
) -> FriendSeriesContext:
    my_wins = 0
    opponent_wins = 0
    game_no = challenge.series_game_number
    best_of = challenge.series_best_of

    if challenge.series_id is not None and challenge.series_best_of > 1:
        async with session_local.begin() as session:
            try:
                (
                    my_wins,
                    opponent_wins,
                    game_no,
                    best_of,
                ) = await game_session_service.get_friend_series_score_for_user(
                    session,
                    user_id=snapshot_user_id,
                    challenge_id=challenge.challenge_id,
                    now_utc=now_utc,
                )
            except (FriendChallengeNotFoundError, FriendChallengeAccessError):
                my_wins = 0
                opponent_wins = 0
                game_no = challenge.series_game_number
                best_of = challenge.series_best_of

    wins_needed = max(1, (best_of // 2) + 1)
    series_finished = (
        best_of <= 1
        or my_wins >= wins_needed
        or opponent_wins >= wins_needed
        or game_no >= best_of
    )
    if my_wins > opponent_wins:
        champion_label = "Du"
    elif opponent_wins > my_wins:
        champion_label = opponent_label
    else:
        champion_label = "Unentschieden"

    return FriendSeriesContext(
        my_wins=my_wins,
        opponent_wins=opponent_wins,
        game_no=game_no,
        best_of=best_of,
        series_finished=series_finished,
        show_next_series_game=(
            challenge.series_id is not None and challenge.series_best_of > 1 and not series_finished
        ),
        champion_label=champion_label,
    )


def resolve_opponent_champion_label(
    *,
    champion_label: str,
    opponent_label: str,
    opponent_label_for_opponent: str,
) -> str:
    if champion_label == "Du":
        return opponent_label_for_opponent
    if champion_label == opponent_label:
        return "Du"
    return champion_label


__all__ = [
    "FriendSeriesContext",
    "resolve_friend_series_context",
    "resolve_opponent_champion_label",
]
