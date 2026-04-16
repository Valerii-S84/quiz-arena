from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.friend_answer_completion_messages import (
    build_opponent_completion_message,
    build_player_completion_message,
)
from app.bot.handlers.gameplay_flows.friend_challenge_result_share import build_result_share_url
from app.bot.keyboards.friend_challenge import build_friend_challenge_finished_keyboard


class Answerable(Protocol):
    async def answer(self, *args, **kwargs) -> object: ...


@dataclass(frozen=True, slots=True)
class FriendCompletionCallbacks:
    resolve_opponent_label: Any
    notify_opponent: Any
    build_friend_score_text: Any
    build_friend_finish_text: Any
    build_public_badge_label: Any
    build_friend_proof_card_text: Any
    enqueue_friend_challenge_proof_cards: Any
    build_series_progress_text: Any


def resolve_answerable(callback: CallbackQuery) -> Answerable:
    message = callback.message
    assert message is not None
    assert hasattr(message, "answer")
    return cast(Answerable, message)


async def send_player_completion_message(
    *,
    callback: CallbackQuery,
    challenge,
    snapshot_user_id: int,
    opponent_label: str,
    answerable: Answerable,
    series_context,
    callbacks: FriendCompletionCallbacks,
) -> None:
    player_message = await build_player_completion_message(
        callback=callback,
        challenge=challenge,
        snapshot_user_id=snapshot_user_id,
        opponent_label=opponent_label,
        series_context=series_context,
        build_result_share_url_fn=build_result_share_url,
        build_finished_keyboard=build_friend_challenge_finished_keyboard,
        build_friend_finish_text=callbacks.build_friend_finish_text,
        build_public_badge_label=callbacks.build_public_badge_label,
        build_friend_proof_card_text=callbacks.build_friend_proof_card_text,
        build_series_progress_text=callbacks.build_series_progress_text,
    )
    await answerable.answer(
        player_message.text,
        reply_markup=player_message.reply_markup,
    )


async def notify_opponent_if_needed(
    *,
    callback: CallbackQuery,
    challenge,
    idempotent_replay: bool,
    opponent_label: str,
    opponent_user_id: int | None,
    callbacks: FriendCompletionCallbacks,
    series_context,
) -> None:
    if idempotent_replay or opponent_user_id is None:
        return

    opponent_label_for_opponent = await callbacks.resolve_opponent_label(
        challenge=challenge,
        user_id=opponent_user_id,
    )
    opponent_message = await build_opponent_completion_message(
        callback=callback,
        challenge=challenge,
        opponent_user_id=opponent_user_id,
        opponent_label=opponent_label,
        opponent_label_for_opponent=opponent_label_for_opponent,
        series_context=series_context,
        build_result_share_url_fn=build_result_share_url,
        build_finished_keyboard=build_friend_challenge_finished_keyboard,
        build_friend_score_text=callbacks.build_friend_score_text,
        build_friend_finish_text=callbacks.build_friend_finish_text,
        build_public_badge_label=callbacks.build_public_badge_label,
        build_friend_proof_card_text=callbacks.build_friend_proof_card_text,
        build_series_progress_text=callbacks.build_series_progress_text,
    )
    await callbacks.notify_opponent(
        callback,
        opponent_user_id=opponent_user_id,
        text=opponent_message.text,
        reply_markup=opponent_message.reply_markup,
    )


__all__ = [
    "Answerable",
    "FriendCompletionCallbacks",
    "notify_opponent_if_needed",
    "resolve_answerable",
    "send_player_completion_message",
]
