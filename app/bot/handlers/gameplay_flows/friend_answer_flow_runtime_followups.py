from __future__ import annotations

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.friend_answer_completion_flow import FriendCompletionCallbacks
from app.bot.keyboards.friend_challenge import build_friend_challenge_start_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.types import AnswerSessionResult, FriendChallengeSnapshot


async def _should_notify_creator_after_opponent_finished(
    *,
    session_local,
    challenge_id,
    target_user_id: int,
    friend_challenges_repo,
) -> bool:
    async with session_local.begin() as session:
        challenge_row = await friend_challenges_repo.get_by_id(session, challenge_id)
    return bool(
        challenge_row is not None
        and challenge_row.creator_user_id == target_user_id
        and challenge_row.opponent_answered_round == challenge_row.total_rounds
        and challenge_row.creator_answered_round == 0
    )


async def maybe_notify_creator_turn(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    context,
    now_utc,
    deps,
    friend_challenges_repo,
    reserve_duel_push_slot,
) -> None:
    if result.idempotent_replay or context.opponent_user_id is None:
        return
    if context.opponent_user_id != context.challenge.creator_user_id:
        return
    if not await _should_notify_creator_after_opponent_finished(
        session_local=deps.session_local,
        challenge_id=context.challenge.challenge_id,
        target_user_id=context.opponent_user_id,
        friend_challenges_repo=friend_challenges_repo,
    ):
        return

    push_reserved = await reserve_duel_push_slot(
        session_local=deps.session_local,
        challenge_id=context.challenge.challenge_id,
        target_user_id=context.opponent_user_id,
        now_utc=now_utc,
    )
    if not push_reserved:
        return

    await deps.notify_opponent(
        callback,
        opponent_user_id=context.opponent_user_id,
        text=TEXTS_DE["msg.friend.challenge.turn.reminder"],
        reply_markup=build_friend_challenge_start_keyboard(
            challenge_id=str(context.challenge.challenge_id)
        ),
    )


def _is_terminal_friend_challenge(challenge: FriendChallengeSnapshot) -> bool:
    return challenge.status in {"COMPLETED", "EXPIRED", "WALKOVER", "CANCELED"}


def _build_completion_callbacks(deps) -> FriendCompletionCallbacks:
    return FriendCompletionCallbacks(
        resolve_opponent_label=deps.resolve_opponent_label,
        notify_opponent=deps.notify_opponent,
        build_friend_score_text=deps.build_friend_score_text,
        build_friend_finish_text=deps.build_friend_finish_text,
        build_public_badge_label=deps.build_public_badge_label,
        build_friend_proof_card_text=deps.build_friend_proof_card_text,
        enqueue_friend_challenge_proof_cards=deps.enqueue_friend_challenge_proof_cards,
        build_series_progress_text=deps.build_series_progress_text,
    )


async def handle_terminal_friend_challenge(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    context,
    now_utc,
    deps,
    handle_completed_friend_challenge,
) -> bool:
    if not _is_terminal_friend_challenge(context.challenge):
        return False

    await handle_completed_friend_challenge(
        callback,
        challenge=context.challenge,
        snapshot_user_id=context.snapshot.user_id,
        opponent_label=context.opponent_label,
        opponent_user_id=context.opponent_user_id,
        now_utc=now_utc,
        idempotent_replay=result.idempotent_replay,
        session_local=deps.session_local,
        game_session_service=deps.game_session_service,
        callbacks=_build_completion_callbacks(deps),
    )
    await callback.answer()
    return True
