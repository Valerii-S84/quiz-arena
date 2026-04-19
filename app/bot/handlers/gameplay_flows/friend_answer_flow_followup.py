from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

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
from app.game.sessions.types import FriendChallengeRoundStartResult, FriendChallengeSnapshot


@dataclass(slots=True)
class StartedFriendRoundPayload:
    snapshot: Any
    round_start: FriendChallengeRoundStartResult


async def _handle_start_round_error(
    callback: CallbackQuery,
    *,
    message: Message,
    challenge: FriendChallengeSnapshot,
    error: Exception,
) -> None:
    if isinstance(error, FriendChallengeExpiredError):
        await message.answer(
            TEXTS_DE["msg.friend.challenge.expired"],
            reply_markup=build_friend_challenge_finished_keyboard(
                challenge_id=str(challenge.challenge_id)
            ),
        )
    else:
        await message.answer(
            TEXTS_DE["msg.friend.challenge.invalid"],
            reply_markup=build_home_keyboard(),
        )
    await callback.answer()


async def start_followup_friend_round(
    callback: CallbackQuery,
    *,
    message: Message,
    telegram_user: TelegramUser,
    context,
    now_utc: datetime,
    deps,
) -> StartedFriendRoundPayload | None:
    async with deps.session_local.begin() as session:
        snapshot = await deps.user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=telegram_user,
        )
        try:
            round_start = await deps.game_session_service.start_friend_challenge_round(
                session,
                user_id=snapshot.user_id,
                challenge_id=context.challenge.challenge_id,
                idempotency_key=f"start:friend:auto:{context.challenge.challenge_id}:{callback.id}",
                now_utc=now_utc,
            )
        except (
            FriendChallengeExpiredError,
            FriendChallengeNotFoundError,
            FriendChallengeAccessError,
            FriendChallengeCompletedError,
            FriendChallengeFullError,
        ) as error:
            await _handle_start_round_error(
                callback,
                message=message,
                challenge=context.challenge,
                error=error,
            )
            return None

    return StartedFriendRoundPayload(
        snapshot=snapshot,
        round_start=round_start,
    )


async def deliver_followup_friend_round(
    callback: CallbackQuery,
    *,
    message: Message,
    context,
    started_round: StartedFriendRoundPayload,
    deps,
) -> None:
    if started_round.round_start.start_result is not None:
        await deps.send_friend_round_question(
            callback,
            snapshot_free_energy=started_round.snapshot.free_energy,
            snapshot_paid_energy=started_round.snapshot.paid_energy,
            round_start=started_round.round_start,
        )
        return

    waiting_text = TEXTS_DE["msg.friend.challenge.all_answered.waiting"].format(
        total_rounds=context.challenge.total_rounds,
        opponent_label=context.opponent_label,
    )
    await message.answer(
        waiting_text,
        reply_markup=build_friend_challenge_back_keyboard(),
    )
