from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from aiogram.types import CallbackQuery, Message

from app.bot.handlers.gameplay_flows.friend_answer_completion_flow import (
    FriendCompletionCallbacks,
    handle_completed_friend_challenge,
)
from app.bot.handlers.gameplay_flows.friend_answer_context import (
    FriendAnswerFlowContext,
    FriendAnswerProgress,
    FriendAnswerRequest,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.types import AnswerSessionResult


async def parse_friend_answer_request(callback: CallbackQuery) -> FriendAnswerRequest | None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return None
    return FriendAnswerRequest(message=cast(Message, callback.message))


async def load_home_snapshot(callback: CallbackQuery, context: FriendAnswerFlowContext) -> Any:
    async with context.services.session_local.begin() as session:
        return await context.services.user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )


async def load_friend_answer_progress(
    callback: CallbackQuery,
    *,
    request: FriendAnswerRequest,
    result: AnswerSessionResult,
    now_utc: datetime,
    context: FriendAnswerFlowContext,
) -> FriendAnswerProgress | None:
    snapshot = await load_home_snapshot(callback, context)
    if result.friend_challenge is None:
        await request.message.answer(
            TEXTS_DE["msg.friend.challenge.invalid"], reply_markup=build_home_keyboard()
        )
        await callback.answer()
        return None

    challenge = result.friend_challenge
    opponent_label = await context.rendering.resolve_opponent_label(
        challenge=challenge,
        user_id=snapshot.user_id,
    )
    await send_friend_answer_summary(
        request.message,
        result=result,
        now_utc=now_utc,
        snapshot_user_id=snapshot.user_id,
        challenge=challenge,
        opponent_label=opponent_label,
        context=context,
    )
    return FriendAnswerProgress(
        snapshot_user_id=snapshot.user_id,
        challenge=challenge,
        opponent_label=opponent_label,
        opponent_user_id=context.rendering.friend_opponent_user_id(
            challenge=challenge,
            user_id=snapshot.user_id,
        ),
    )


async def send_friend_answer_summary(
    message: Message,
    *,
    result: AnswerSessionResult,
    now_utc: datetime,
    snapshot_user_id: int,
    challenge: Any,
    opponent_label: str,
    context: FriendAnswerFlowContext,
) -> None:
    await message.answer(
        context.rendering.build_friend_score_text(
            challenge=challenge,
            user_id=snapshot_user_id,
            opponent_label=opponent_label,
        )
    )
    ttl_text = context.rendering.build_friend_ttl_text(challenge=challenge, now_utc=now_utc)
    if ttl_text is not None:
        await message.answer(ttl_text)

    if result.friend_challenge_round_completed:
        round_result_text = TEXTS_DE["msg.friend.challenge.round.result"].format(
            round_no=(result.friend_challenge_answered_round or challenge.current_round)
        )
        await message.answer(round_result_text)


async def continue_completed_friend_challenge(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    now_utc: datetime,
    progress: FriendAnswerProgress,
    context: FriendAnswerFlowContext,
) -> None:
    await handle_completed_friend_challenge(
        callback,
        challenge=progress.challenge,
        snapshot_user_id=progress.snapshot_user_id,
        opponent_label=progress.opponent_label,
        opponent_user_id=progress.opponent_user_id,
        now_utc=now_utc,
        idempotent_replay=result.idempotent_replay,
        session_local=context.services.session_local,
        game_session_service=context.services.game_session_service,
        callbacks=FriendCompletionCallbacks(
            resolve_opponent_label=context.rendering.resolve_opponent_label,
            notify_opponent=context.actions.notify_opponent,
            build_friend_score_text=context.rendering.build_friend_score_text,
            build_friend_finish_text=context.rendering.build_friend_finish_text,
            build_public_badge_label=context.rendering.build_public_badge_label,
            build_friend_proof_card_text=context.rendering.build_friend_proof_card_text,
            enqueue_friend_challenge_proof_cards=context.actions.enqueue_friend_challenge_proof_cards,
            build_series_progress_text=context.rendering.build_series_progress_text,
        ),
    )
