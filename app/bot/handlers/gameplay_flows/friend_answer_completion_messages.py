from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.bot.texts.de import TEXTS_DE

from .friend_answer_completion_state import FriendSeriesContext, resolve_opponent_champion_label


@dataclass(frozen=True, slots=True)
class FriendCompletionMessage:
    text: str
    reply_markup: object


def _append_series_lines(
    lines: list[str],
    *,
    context: FriendSeriesContext,
    opponent_label: str,
    champion_label: str,
    build_series_progress_text: Callable[..., str],
) -> None:
    if context.best_of <= 1:
        return
    lines.append(
        build_series_progress_text(
            game_no=context.game_no,
            best_of=context.best_of,
            my_wins=context.my_wins,
            opponent_wins=context.opponent_wins,
            opponent_label=opponent_label,
        )
    )
    if context.series_finished:
        lines.append(
            TEXTS_DE["msg.friend.challenge.series.finished"].format(champion_label=champion_label)
        )


async def build_player_completion_message(
    *,
    callback: Any,
    challenge: Any,
    snapshot_user_id: int,
    opponent_label: str,
    series_context: FriendSeriesContext,
    build_result_share_url_fn: Callable[..., Awaitable[str | None]],
    build_finished_keyboard: Callable[..., object],
    build_friend_finish_text: Callable[..., str],
    build_public_badge_label: Callable[..., str],
    build_friend_proof_card_text: Callable[..., str],
    build_series_progress_text: Callable[..., str],
) -> FriendCompletionMessage:
    finish_text = build_friend_finish_text(
        challenge=challenge,
        user_id=snapshot_user_id,
        opponent_label=opponent_label,
    )
    badge_label = build_public_badge_label(
        challenge=challenge,
        user_id=snapshot_user_id,
        series_my_wins=series_context.my_wins,
        series_opponent_wins=series_context.opponent_wins,
    )
    proof_card_text = build_friend_proof_card_text(
        challenge=challenge,
        user_id=snapshot_user_id,
        opponent_label=opponent_label,
    )
    share_url = await build_result_share_url_fn(
        callback=callback,
        proof_card_text=proof_card_text,
    )
    keyboard = build_finished_keyboard(
        challenge_id=str(challenge.challenge_id),
        share_url=share_url,
        show_next_series_game=series_context.show_next_series_game,
    )
    lines = [finish_text]
    _append_series_lines(
        lines,
        context=series_context,
        opponent_label=opponent_label,
        champion_label=series_context.champion_label,
        build_series_progress_text=build_series_progress_text,
    )
    lines.append(TEXTS_DE["msg.friend.challenge.badge.public"].format(badge_label=badge_label))
    lines.append("")
    lines.append(proof_card_text)
    return FriendCompletionMessage(text="\n".join(lines), reply_markup=keyboard)


async def build_opponent_completion_message(
    *,
    callback: Any,
    challenge: Any,
    opponent_user_id: int,
    opponent_label: str,
    opponent_label_for_opponent: str,
    series_context: FriendSeriesContext,
    build_result_share_url_fn: Callable[..., Awaitable[str | None]],
    build_finished_keyboard: Callable[..., object],
    build_friend_score_text: Callable[..., str],
    build_friend_finish_text: Callable[..., str],
    build_public_badge_label: Callable[..., str],
    build_friend_proof_card_text: Callable[..., str],
    build_series_progress_text: Callable[..., str],
) -> FriendCompletionMessage:
    badge_label = build_public_badge_label(
        challenge=challenge,
        user_id=opponent_user_id,
        series_my_wins=series_context.opponent_wins,
        series_opponent_wins=series_context.my_wins,
    )
    proof_card_text = build_friend_proof_card_text(
        challenge=challenge,
        user_id=opponent_user_id,
        opponent_label=opponent_label_for_opponent,
    )
    share_url = await build_result_share_url_fn(
        callback=callback,
        proof_card_text=proof_card_text,
    )
    keyboard = build_finished_keyboard(
        challenge_id=str(challenge.challenge_id),
        share_url=share_url,
        show_next_series_game=series_context.show_next_series_game,
    )
    del build_friend_score_text
    lines = [
        build_friend_finish_text(
            challenge=challenge,
            user_id=opponent_user_id,
            opponent_label=opponent_label_for_opponent,
        ),
    ]
    _append_series_lines(
        lines,
        context=FriendSeriesContext(
            my_wins=series_context.opponent_wins,
            opponent_wins=series_context.my_wins,
            game_no=series_context.game_no,
            best_of=series_context.best_of,
            series_finished=series_context.series_finished,
            show_next_series_game=series_context.show_next_series_game,
            champion_label=resolve_opponent_champion_label(
                champion_label=series_context.champion_label,
                opponent_label=opponent_label,
                opponent_label_for_opponent=opponent_label_for_opponent,
            ),
        ),
        opponent_label=opponent_label_for_opponent,
        champion_label=resolve_opponent_champion_label(
            champion_label=series_context.champion_label,
            opponent_label=opponent_label,
            opponent_label_for_opponent=opponent_label_for_opponent,
        ),
        build_series_progress_text=build_series_progress_text,
    )
    lines.append(TEXTS_DE["msg.friend.challenge.badge.public"].format(badge_label=badge_label))
    lines.append("")
    lines.append(proof_card_text)
    return FriendCompletionMessage(text="\n".join(lines), reply_markup=keyboard)


__all__ = [
    "FriendCompletionMessage",
    "build_opponent_completion_message",
    "build_player_completion_message",
]
