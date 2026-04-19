from __future__ import annotations

from datetime import datetime

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.friend_answer_completion_context import (
    FriendCompletionContext,
    resolve_completion_context,
)
from app.bot.handlers.gameplay_flows.friend_answer_completion_delivery import (
    FriendCompletionCallbacks,
    notify_opponent_if_needed,
    send_player_completion_message,
)
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
    answerable,
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


def _enqueue_proof_cards_if_needed(
    *,
    challenge,
    idempotent_replay: bool,
    callbacks: FriendCompletionCallbacks,
) -> None:
    if idempotent_replay:
        return
    callbacks.enqueue_friend_challenge_proof_cards(challenge_id=str(challenge.challenge_id))


async def _deliver_standard_completion(
    *,
    callback: CallbackQuery,
    challenge,
    snapshot_user_id: int,
    opponent_label: str,
    opponent_user_id: int | None,
    idempotent_replay: bool,
    completion_context: FriendCompletionContext,
    callbacks: FriendCompletionCallbacks,
) -> None:
    await send_player_completion_message(
        callback=callback,
        challenge=challenge,
        snapshot_user_id=snapshot_user_id,
        opponent_label=opponent_label,
        answerable=completion_context.answerable,
        series_context=completion_context.series_context,
        callbacks=callbacks,
    )
    await notify_opponent_if_needed(
        callback=callback,
        challenge=challenge,
        idempotent_replay=idempotent_replay,
        opponent_label=opponent_label,
        opponent_user_id=opponent_user_id,
        callbacks=callbacks,
        series_context=completion_context.series_context,
    )
    _enqueue_proof_cards_if_needed(
        challenge=challenge,
        idempotent_replay=idempotent_replay,
        callbacks=callbacks,
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
    completion_context = await resolve_completion_context(
        callback,
        challenge=challenge,
        snapshot_user_id=snapshot_user_id,
        opponent_label=opponent_label,
        now_utc=now_utc,
        session_local=session_local,
        game_session_service=game_session_service,
    )
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
        answerable=completion_context.answerable,
    ):
        return
    await _deliver_standard_completion(
        callback=callback,
        challenge=challenge,
        snapshot_user_id=snapshot_user_id,
        opponent_label=opponent_label,
        opponent_user_id=opponent_user_id,
        idempotent_replay=idempotent_replay,
        completion_context=completion_context,
        callbacks=callbacks,
    )
