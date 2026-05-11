from __future__ import annotations

from datetime import datetime

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.friend_answer_context import (
    FriendAnswerFlowActions,
    FriendAnswerFlowContext,
    FriendAnswerFlowRendering,
    FriendAnswerFlowServices,
)
from app.bot.handlers.gameplay_flows.friend_answer_next import (
    send_next_round_or_waiting,
    start_next_friend_round,
)
from app.bot.handlers.gameplay_flows.friend_answer_notifications import (
    maybe_notify_creator_after_opponent_finished,
)
from app.bot.handlers.gameplay_flows.friend_answer_progress import (
    continue_completed_friend_challenge,
    load_friend_answer_progress,
    parse_friend_answer_request,
)
from app.game.sessions.types import AnswerSessionResult

TERMINAL_FRIEND_CHALLENGE_STATUSES = {"COMPLETED", "EXPIRED", "WALKOVER", "CANCELED"}

__all__ = [
    "FriendAnswerFlowActions",
    "FriendAnswerFlowContext",
    "FriendAnswerFlowRendering",
    "FriendAnswerFlowServices",
    "handle_friend_answer_branch",
]


async def handle_friend_answer_branch(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    now_utc: datetime,
    context: FriendAnswerFlowContext,
) -> None:
    request = await parse_friend_answer_request(callback)
    if request is None:
        return

    progress = await load_friend_answer_progress(
        callback,
        request=request,
        result=result,
        now_utc=now_utc,
        context=context,
    )
    if progress is None:
        return

    await maybe_notify_creator_after_opponent_finished(
        callback,
        result=result,
        now_utc=now_utc,
        progress=progress,
        context=context,
    )

    if progress.challenge.status in TERMINAL_FRIEND_CHALLENGE_STATUSES:
        await continue_completed_friend_challenge(
            callback,
            result=result,
            now_utc=now_utc,
            progress=progress,
            context=context,
        )
        await callback.answer()
        return

    started_round = await start_next_friend_round(
        callback,
        request=request,
        challenge=progress.challenge,
        now_utc=now_utc,
        context=context,
    )
    if started_round is None:
        return

    await send_next_round_or_waiting(
        callback,
        request=request,
        progress=progress,
        started_round=started_round,
        context=context,
    )
    await callback.answer()
