from __future__ import annotations

from typing import Any

from aiogram.types import CallbackQuery

from .friend_series_flow_common import build_series_reply_markup


def build_series_next_text(
    *,
    next_duel: Any,
    opponent_label: str,
    game_no: int,
    best_of: int,
    my_wins: int,
    opponent_wins: int,
    build_friend_plan_text,
    build_series_progress_text,
) -> str:
    return "\n".join(
        [
            build_series_progress_text(
                game_no=game_no,
                best_of=best_of,
                my_wins=my_wins,
                opponent_wins=opponent_wins,
                opponent_label=opponent_label,
            ),
            build_friend_plan_text(total_rounds=next_duel.total_rounds),
        ]
    )


async def send_series_next_message(
    *,
    message: Any,
    next_duel: Any,
    opponent_label: str,
    game_no: int,
    best_of: int,
    my_wins: int,
    opponent_wins: int,
    build_friend_plan_text,
    build_series_progress_text,
) -> None:
    await message.answer(
        build_series_next_text(
            next_duel=next_duel,
            opponent_label=opponent_label,
            game_no=game_no,
            best_of=best_of,
            my_wins=my_wins,
            opponent_wins=opponent_wins,
            build_friend_plan_text=build_friend_plan_text,
            build_series_progress_text=build_series_progress_text,
        ),
        reply_markup=build_series_reply_markup(challenge_id=str(next_duel.challenge_id)),
    )


async def notify_series_next_opponent(
    *,
    callback: CallbackQuery,
    next_duel: Any,
    viewer_user_id: int,
    game_no: int,
    best_of: int,
    my_wins: int,
    opponent_wins: int,
    resolve_opponent_label,
    friend_opponent_user_id,
    notify_opponent,
    build_friend_plan_text,
    build_series_progress_text,
) -> None:
    opponent_user_id = friend_opponent_user_id(challenge=next_duel, user_id=viewer_user_id)
    if opponent_user_id is None:
        return
    opponent_label = await resolve_opponent_label(challenge=next_duel, user_id=opponent_user_id)
    await notify_opponent(
        callback,
        opponent_user_id=opponent_user_id,
        text=build_series_next_text(
            next_duel=next_duel,
            opponent_label=opponent_label,
            game_no=game_no,
            best_of=best_of,
            my_wins=opponent_wins,
            opponent_wins=my_wins,
            build_friend_plan_text=build_friend_plan_text,
            build_series_progress_text=build_series_progress_text,
        ),
        reply_markup=build_series_reply_markup(challenge_id=str(next_duel.challenge_id)),
    )


__all__ = [
    "build_series_next_text",
    "notify_series_next_opponent",
    "send_series_next_message",
]
