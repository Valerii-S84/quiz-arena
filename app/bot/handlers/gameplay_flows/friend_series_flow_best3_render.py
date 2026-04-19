from __future__ import annotations

from typing import Any

from aiogram.types import CallbackQuery

from app.bot.texts.de import TEXTS_DE

from .friend_series_flow_common import build_series_reply_markup


def build_series_best3_text(
    *,
    series_duel: Any,
    opponent_label: str,
    build_friend_plan_text,
    build_series_progress_text,
) -> str:
    return "\n".join(
        [
            TEXTS_DE["msg.friend.challenge.series.started"].format(opponent_label=opponent_label),
            build_friend_plan_text(total_rounds=series_duel.total_rounds),
            build_series_progress_text(
                game_no=series_duel.series_game_number,
                best_of=series_duel.series_best_of,
                my_wins=0,
                opponent_wins=0,
                opponent_label=opponent_label,
            ),
        ]
    )


async def send_series_best3_message(
    *,
    message: Any,
    series_duel: Any,
    opponent_label: str,
    build_friend_plan_text,
    build_series_progress_text,
) -> None:
    await message.answer(
        build_series_best3_text(
            series_duel=series_duel,
            opponent_label=opponent_label,
            build_friend_plan_text=build_friend_plan_text,
            build_series_progress_text=build_series_progress_text,
        ),
        reply_markup=build_series_reply_markup(challenge_id=str(series_duel.challenge_id)),
    )


async def notify_series_best3_opponent(
    *,
    callback: CallbackQuery,
    series_duel: Any,
    viewer_user_id: int,
    resolve_opponent_label,
    friend_opponent_user_id,
    notify_opponent,
    build_friend_plan_text,
    build_series_progress_text,
) -> None:
    opponent_user_id = friend_opponent_user_id(challenge=series_duel, user_id=viewer_user_id)
    if opponent_user_id is None:
        return
    opponent_label = await resolve_opponent_label(challenge=series_duel, user_id=opponent_user_id)
    await notify_opponent(
        callback,
        opponent_user_id=opponent_user_id,
        text=build_series_best3_text(
            series_duel=series_duel,
            opponent_label=opponent_label,
            build_friend_plan_text=build_friend_plan_text,
            build_series_progress_text=build_series_progress_text,
        ),
        reply_markup=build_series_reply_markup(challenge_id=str(series_duel.challenge_id)),
    )


__all__ = [
    "build_series_best3_text",
    "notify_series_best3_opponent",
    "send_series_best3_message",
]
