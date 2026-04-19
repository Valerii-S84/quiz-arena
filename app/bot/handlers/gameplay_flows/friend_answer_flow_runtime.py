from __future__ import annotations

from datetime import datetime

from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

from app.bot.handlers.gameplay_flows import friend_answer_flow_followup
from app.bot.handlers.gameplay_flows.friend_answer_flow_runtime_context import (
    load_friend_answer_context,
    send_friend_progress_messages,
    send_invalid_friend_challenge_message,
)
from app.bot.handlers.gameplay_flows.friend_answer_flow_runtime_followups import (
    handle_terminal_friend_challenge,
    maybe_notify_creator_turn,
)
from app.game.sessions.types import AnswerSessionResult


async def _resolve_context_or_notify_invalid(
    callback: CallbackQuery,
    *,
    message: Message,
    telegram_user: TelegramUser,
    result: AnswerSessionResult,
    deps,
):
    context = await load_friend_answer_context(
        session_local=deps.session_local,
        user_onboarding_service=deps.user_onboarding_service,
        telegram_user=telegram_user,
        result=result,
        resolve_opponent_label=deps.resolve_opponent_label,
        friend_opponent_user_id=deps.friend_opponent_user_id,
    )
    if context is None:
        await send_invalid_friend_challenge_message(callback, message=message)
    return context


async def _start_and_deliver_followup_round(
    callback: CallbackQuery,
    *,
    message: Message,
    telegram_user: TelegramUser,
    context,
    now_utc: datetime,
    deps,
) -> None:
    started_round = await friend_answer_flow_followup.start_followup_friend_round(
        callback,
        message=message,
        telegram_user=telegram_user,
        context=context,
        now_utc=now_utc,
        deps=deps,
    )
    if started_round is None:
        return

    await friend_answer_flow_followup.deliver_followup_friend_round(
        callback,
        message=message,
        context=context,
        started_round=started_round,
        deps=deps,
    )
    await callback.answer()


async def _handle_resolved_friend_answer(
    callback: CallbackQuery,
    *,
    message: Message,
    telegram_user: TelegramUser,
    result: AnswerSessionResult,
    context,
    now_utc: datetime,
    deps,
    friend_challenges_repo,
    reserve_duel_push_slot,
    handle_completed_friend_challenge,
) -> None:
    await send_friend_progress_messages(
        message,
        result=result,
        context=context,
        now_utc=now_utc,
        deps=deps,
    )
    await maybe_notify_creator_turn(
        callback,
        result=result,
        context=context,
        now_utc=now_utc,
        deps=deps,
        friend_challenges_repo=friend_challenges_repo,
        reserve_duel_push_slot=reserve_duel_push_slot,
    )
    await _finish_or_continue_friend_answer(
        callback,
        message=message,
        telegram_user=telegram_user,
        result=result,
        context=context,
        now_utc=now_utc,
        deps=deps,
        handle_completed_friend_challenge=handle_completed_friend_challenge,
    )


async def _finish_or_continue_friend_answer(
    callback: CallbackQuery,
    *,
    message: Message,
    telegram_user: TelegramUser,
    result: AnswerSessionResult,
    context,
    now_utc: datetime,
    deps,
    handle_completed_friend_challenge,
) -> None:
    if await handle_terminal_friend_challenge(
        callback,
        result=result,
        context=context,
        now_utc=now_utc,
        deps=deps,
        handle_completed_friend_challenge=handle_completed_friend_challenge,
    ):
        return

    await _start_and_deliver_followup_round(
        callback,
        message=message,
        telegram_user=telegram_user,
        context=context,
        now_utc=now_utc,
        deps=deps,
    )


async def run_friend_answer_branch(
    callback: CallbackQuery,
    *,
    message: Message,
    telegram_user: TelegramUser,
    result: AnswerSessionResult,
    now_utc: datetime,
    deps,
    friend_challenges_repo,
    reserve_duel_push_slot,
    handle_completed_friend_challenge,
) -> None:
    context = await _resolve_context_or_notify_invalid(
        callback,
        message=message,
        telegram_user=telegram_user,
        result=result,
        deps=deps,
    )
    if context is None:
        return

    await _handle_resolved_friend_answer(
        callback,
        message=message,
        telegram_user=telegram_user,
        result=result,
        context=context,
        now_utc=now_utc,
        deps=deps,
        friend_challenges_repo=friend_challenges_repo,
        reserve_duel_push_slot=reserve_duel_push_slot,
        handle_completed_friend_challenge=handle_completed_friend_challenge,
    )
