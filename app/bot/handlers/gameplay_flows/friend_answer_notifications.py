from __future__ import annotations

from datetime import datetime
from typing import Any

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.friend_answer_context import (
    FriendAnswerFlowContext,
    FriendAnswerProgress,
)
from app.bot.handlers.gameplay_flows.friend_challenge_push_quota import reserve_duel_push_slot
from app.bot.keyboards.friend_challenge import build_friend_challenge_start_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.sessions.types import AnswerSessionResult


async def should_notify_creator_after_opponent_finished(
    *,
    session_local: Any,
    challenge_id: Any,
    target_user_id: int,
) -> bool:
    async with session_local.begin() as session:
        challenge_row = await FriendChallengesRepo.get_by_id(session, challenge_id)
    return bool(
        challenge_row is not None
        and challenge_row.creator_user_id == target_user_id
        and challenge_row.opponent_answered_round == challenge_row.total_rounds
        and challenge_row.creator_answered_round == 0
    )


async def maybe_notify_creator_after_opponent_finished(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    now_utc: datetime,
    progress: FriendAnswerProgress,
    context: FriendAnswerFlowContext,
) -> None:
    if (
        not result.idempotent_replay
        and progress.opponent_user_id is not None
        and progress.opponent_user_id == progress.challenge.creator_user_id
        and await should_notify_creator_after_opponent_finished(
            session_local=context.services.session_local,
            challenge_id=progress.challenge.challenge_id,
            target_user_id=progress.opponent_user_id,
        )
    ):
        push_reserved = await reserve_duel_push_slot(
            session_local=context.services.session_local,
            challenge_id=progress.challenge.challenge_id,
            target_user_id=progress.opponent_user_id,
            now_utc=now_utc,
        )
        if push_reserved:
            await context.actions.notify_opponent(
                callback,
                opponent_user_id=progress.opponent_user_id,
                text=TEXTS_DE["msg.friend.challenge.turn.reminder"],
                reply_markup=build_friend_challenge_start_keyboard(
                    challenge_id=str(progress.challenge.challenge_id)
                ),
            )
