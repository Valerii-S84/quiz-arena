from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.friend_answer_completion_messages import (
    build_opponent_completion_message,
    build_player_completion_message,
)
from app.bot.handlers.gameplay_flows.friend_answer_completion_state import (
    resolve_friend_series_context,
)
from app.bot.handlers.gameplay_flows.friend_challenge_result_share import build_result_share_url
from app.bot.handlers.gameplay_flows.tournament_match_completion import (
    handle_completed_tournament_match,
)
from app.bot.handlers.gameplay_flows.tournament_match_post_flow import (
    build_tournament_post_match_keyboard,
    build_tournament_post_match_text,
    enqueue_tournament_post_match_updates,
    resolve_tournament_id_for_match,
    resolve_tournament_place_for_user,
    resolve_tournament_view_callback_data_for_match,
)
from app.bot.keyboards.friend_challenge import build_friend_challenge_finished_keyboard


class _Answerable(Protocol):
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


def _resolve_answerable(callback: CallbackQuery) -> _Answerable:
    message = callback.message
    assert message is not None
    assert hasattr(message, "answer")
    return cast(_Answerable, message)


async def _handle_tournament_completion(
    *,
    callback: CallbackQuery,
    challenge,
    snapshot_user_id: int,
    opponent_label: str,
    opponent_user_id: int | None,
    idempotent_replay: bool,
    session_local,
    resolve_opponent_label,
    notify_opponent,
    answerable: _Answerable,
) -> bool:
    return await handle_completed_tournament_match(
        callback,
        challenge=challenge,
        snapshot_user_id=snapshot_user_id,
        opponent_label=opponent_label,
        opponent_user_id=opponent_user_id,
        idempotent_replay=idempotent_replay,
        answerable=answerable,
        session_local=session_local,
        resolve_opponent_label=resolve_opponent_label,
        notify_opponent=notify_opponent,
        resolve_tournament_id_for_match=resolve_tournament_id_for_match,
        resolve_tournament_view_callback_data_for_match=resolve_tournament_view_callback_data_for_match,
        resolve_tournament_place_for_user=resolve_tournament_place_for_user,
        build_tournament_post_match_keyboard=build_tournament_post_match_keyboard,
        build_tournament_post_match_text=build_tournament_post_match_text,
        enqueue_tournament_post_match_updates=enqueue_tournament_post_match_updates,
    )


async def _send_player_completion_message(
    *,
    callback: CallbackQuery,
    challenge,
    snapshot_user_id: int,
    opponent_label: str,
    answerable: _Answerable,
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


async def _notify_opponent_if_needed(
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


async def handle_completed_friend_challenge(
    callback: CallbackQuery,
    *,
    challenge,
    snapshot_user_id: int,
    opponent_label: str,
    opponent_user_id: int | None,
    now_utc: datetime,
    idempotent_replay: bool,
    session_local,
    game_session_service,
    callbacks: FriendCompletionCallbacks,
) -> None:
    series_context = await resolve_friend_series_context(
        challenge=challenge,
        snapshot_user_id=snapshot_user_id,
        opponent_label=opponent_label,
        now_utc=now_utc,
        session_local=session_local,
        game_session_service=game_session_service,
    )
    answerable = _resolve_answerable(callback)
    if await _handle_tournament_completion(
        challenge=challenge,
        callback=callback,
        snapshot_user_id=snapshot_user_id,
        opponent_label=opponent_label,
        opponent_user_id=opponent_user_id,
        idempotent_replay=idempotent_replay,
        session_local=session_local,
        resolve_opponent_label=callbacks.resolve_opponent_label,
        notify_opponent=callbacks.notify_opponent,
        answerable=answerable,
    ):
        return
    await _send_player_completion_message(
        callback=callback,
        challenge=challenge,
        snapshot_user_id=snapshot_user_id,
        opponent_label=opponent_label,
        answerable=answerable,
        series_context=series_context,
        callbacks=callbacks,
    )
    await _notify_opponent_if_needed(
        callback=callback,
        challenge=challenge,
        idempotent_replay=idempotent_replay,
        opponent_label=opponent_label,
        opponent_user_id=opponent_user_id,
        callbacks=callbacks,
        series_context=series_context,
    )
    if not idempotent_replay:
        callbacks.enqueue_friend_challenge_proof_cards(challenge_id=str(challenge.challenge_id))
