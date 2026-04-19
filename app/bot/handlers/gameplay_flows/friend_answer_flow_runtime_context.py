from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.types import AnswerSessionResult, FriendChallengeSnapshot
from app.services.user_onboarding import HomeSnapshot


@dataclass(slots=True)
class FriendAnswerContext:
    snapshot: HomeSnapshot
    challenge: FriendChallengeSnapshot
    opponent_label: str
    opponent_user_id: int | None


async def _load_home_snapshot(
    *,
    session_local,
    user_onboarding_service,
    telegram_user: TelegramUser,
) -> HomeSnapshot:
    async with session_local.begin() as session:
        return await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=telegram_user,
        )


async def load_friend_answer_context(
    *,
    session_local,
    user_onboarding_service,
    telegram_user: TelegramUser,
    result: AnswerSessionResult,
    resolve_opponent_label,
    friend_opponent_user_id,
) -> FriendAnswerContext | None:
    if result.friend_challenge is None:
        return None

    snapshot = await _load_home_snapshot(
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        telegram_user=telegram_user,
    )
    challenge = result.friend_challenge
    opponent_label = await resolve_opponent_label(
        challenge=challenge,
        user_id=snapshot.user_id,
    )
    return FriendAnswerContext(
        snapshot=snapshot,
        challenge=challenge,
        opponent_label=opponent_label,
        opponent_user_id=friend_opponent_user_id(
            challenge=challenge,
            user_id=snapshot.user_id,
        ),
    )


async def send_invalid_friend_challenge_message(
    callback: CallbackQuery,
    *,
    message: Message,
) -> None:
    await message.answer(
        TEXTS_DE["msg.friend.challenge.invalid"],
        reply_markup=build_home_keyboard(),
    )
    await callback.answer()


def _build_friend_round_result_text(
    *,
    result: AnswerSessionResult,
    challenge: FriendChallengeSnapshot,
) -> str:
    return TEXTS_DE["msg.friend.challenge.round.result"].format(
        round_no=(result.friend_challenge_answered_round or challenge.current_round)
    )


async def send_friend_progress_messages(
    message: Message,
    *,
    result: AnswerSessionResult,
    context: FriendAnswerContext,
    now_utc: datetime,
    deps,
) -> None:
    await message.answer(
        deps.build_friend_score_text(
            challenge=context.challenge,
            user_id=context.snapshot.user_id,
            opponent_label=context.opponent_label,
        )
    )
    ttl_text = deps.build_friend_ttl_text(challenge=context.challenge, now_utc=now_utc)
    if ttl_text is not None:
        await message.answer(ttl_text)
    if result.friend_challenge_round_completed:
        await message.answer(
            _build_friend_round_result_text(
                result=result,
                challenge=context.challenge,
            )
        )
