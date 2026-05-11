from __future__ import annotations

from datetime import datetime
from typing import Any

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.friend_answer_context import (
    FriendAnswerFlowContext,
    FriendAnswerProgress,
    FriendAnswerRequest,
    StartedFriendRound,
)
from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_finished_keyboard,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)


async def start_next_friend_round(
    callback: CallbackQuery,
    *,
    request: FriendAnswerRequest,
    challenge: Any,
    now_utc: datetime,
    context: FriendAnswerFlowContext,
) -> StartedFriendRound | None:
    async with context.services.session_local.begin() as session:
        snapshot = await context.services.user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            round_start = await context.services.game_session_service.start_friend_challenge_round(
                session,
                user_id=snapshot.user_id,
                challenge_id=challenge.challenge_id,
                idempotency_key=f"start:friend:auto:{challenge.challenge_id}:{callback.id}",
                now_utc=now_utc,
            )
        except FriendChallengeExpiredError:
            await request.message.answer(
                TEXTS_DE["msg.friend.challenge.expired"],
                reply_markup=build_friend_challenge_finished_keyboard(
                    challenge_id=str(challenge.challenge_id)
                ),
            )
            await callback.answer()
            return None
        except (
            FriendChallengeNotFoundError,
            FriendChallengeAccessError,
            FriendChallengeCompletedError,
            FriendChallengeFullError,
        ):
            await request.message.answer(
                TEXTS_DE["msg.friend.challenge.invalid"],
                reply_markup=build_home_keyboard(),
            )
            await callback.answer()
            return None
    return StartedFriendRound(snapshot=snapshot, round_start=round_start)


async def send_next_round_or_waiting(
    callback: CallbackQuery,
    *,
    request: FriendAnswerRequest,
    progress: FriendAnswerProgress,
    started_round: StartedFriendRound,
    context: FriendAnswerFlowContext,
) -> None:
    if started_round.round_start.start_result is not None:
        await context.actions.send_friend_round_question(
            callback,
            snapshot_free_energy=started_round.snapshot.free_energy,
            snapshot_paid_energy=started_round.snapshot.paid_energy,
            round_start=started_round.round_start,
        )
        return

    waiting_text = TEXTS_DE["msg.friend.challenge.all_answered.waiting"].format(
        total_rounds=progress.challenge.total_rounds,
        opponent_label=progress.opponent_label,
    )
    await request.message.answer(
        waiting_text,
        reply_markup=build_friend_challenge_back_keyboard(
            challenge=started_round.round_start.snapshot,
            user_id=started_round.snapshot.user_id,
        ),
    )
