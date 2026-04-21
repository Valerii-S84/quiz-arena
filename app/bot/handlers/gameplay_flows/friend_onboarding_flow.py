from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, cast

from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_finished_info_keyboard,
    build_friend_challenge_finished_keyboard,
    build_friend_challenge_onboarding_info_keyboard,
    build_friend_challenge_onboarding_keyboard,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.friend_challenges.constants import DUEL_STATUS_EXPIRED
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeExpiredError,
    FriendChallengeNotFoundError,
)


class AnswerableMessage(Protocol):
    async def answer(self, *args, **kwargs) -> object: ...


def _resolve_answerable_message(callback: CallbackQuery) -> AnswerableMessage:
    message = callback.message
    assert message is not None
    assert hasattr(message, "answer")
    return cast(AnswerableMessage, message)


async def _load_friend_challenge_context(
    callback: CallbackQuery,
    *,
    callback_pattern,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
):
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return None

    challenge_id = parse_uuid_callback(pattern=callback_pattern, callback_data=callback.data)
    if challenge_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return None

    answerable_message = _resolve_answerable_message(callback)
    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            challenge = await game_session_service.get_friend_challenge_snapshot_for_user(
                session,
                user_id=snapshot.user_id,
                challenge_id=challenge_id,
                now_utc=now_utc,
            )
            if challenge.status == DUEL_STATUS_EXPIRED:
                await answerable_message.answer(
                    TEXTS_DE["msg.friend.challenge.expired"],
                    reply_markup=build_friend_challenge_finished_keyboard(
                        challenge_id=str(challenge_id)
                    ),
                )
                await callback.answer()
                return None
        except FriendChallengeExpiredError:
            await answerable_message.answer(
                TEXTS_DE["msg.friend.challenge.expired"],
                reply_markup=build_friend_challenge_finished_keyboard(
                    challenge_id=str(challenge_id)
                ),
            )
            await callback.answer()
            return None
        except (
            FriendChallengeNotFoundError,
            FriendChallengeAccessError,
        ):
            await answerable_message.answer(
                TEXTS_DE["msg.friend.challenge.invalid"],
                reply_markup=build_home_keyboard(),
            )
            await callback.answer()
            return None

    return snapshot.user_id, challenge


async def handle_friend_challenge_onboarding_show(
    callback: CallbackQuery,
    *,
    friend_onboarding_show_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
    resolve_opponent_label,
) -> None:
    context = await _load_friend_challenge_context(
        callback,
        callback_pattern=friend_onboarding_show_re,
        parse_uuid_callback=parse_uuid_callback,
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        game_session_service=game_session_service,
    )
    if context is None:
        return

    answerable_message = _resolve_answerable_message(callback)
    user_id, challenge = context
    opponent_label = await resolve_opponent_label(challenge=challenge, user_id=user_id)
    await answerable_message.answer(
        TEXTS_DE["msg.friend.challenge.onboarding"].format(challenger_name=opponent_label),
        reply_markup=build_friend_challenge_onboarding_keyboard(
            challenge_id=str(challenge.challenge_id)
        ),
    )
    await callback.answer()


async def handle_friend_challenge_onboarding_info(
    callback: CallbackQuery,
    *,
    friend_onboarding_info_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
) -> None:
    context = await _load_friend_challenge_context(
        callback,
        callback_pattern=friend_onboarding_info_re,
        parse_uuid_callback=parse_uuid_callback,
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        game_session_service=game_session_service,
    )
    if context is None:
        return

    answerable_message = _resolve_answerable_message(callback)
    _, challenge = context
    await answerable_message.answer(
        TEXTS_DE["msg.friend.challenge.info"],
        reply_markup=build_friend_challenge_onboarding_info_keyboard(
            challenge_id=str(challenge.challenge_id)
        ),
    )
    await callback.answer()


async def handle_friend_challenge_finished_show(
    callback: CallbackQuery,
    *,
    friend_finished_show_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
    resolve_opponent_label,
    build_friend_score_text,
    build_friend_finish_text,
) -> None:
    context = await _load_friend_challenge_context(
        callback,
        callback_pattern=friend_finished_show_re,
        parse_uuid_callback=parse_uuid_callback,
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        game_session_service=game_session_service,
    )
    if context is None:
        return

    answerable_message = _resolve_answerable_message(callback)
    user_id, challenge = context
    opponent_label = await resolve_opponent_label(challenge=challenge, user_id=user_id)
    lines = [
        build_friend_score_text(
            challenge=challenge,
            user_id=user_id,
            opponent_label=opponent_label,
        ),
        build_friend_finish_text(
            challenge=challenge,
            user_id=user_id,
            opponent_label=opponent_label,
        ),
    ]
    await answerable_message.answer(
        "\n".join(lines),
        reply_markup=build_friend_challenge_finished_keyboard(
            challenge_id=str(challenge.challenge_id)
        ),
    )
    await callback.answer()


async def handle_friend_challenge_finished_info(
    callback: CallbackQuery,
    *,
    friend_finished_info_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
) -> None:
    context = await _load_friend_challenge_context(
        callback,
        callback_pattern=friend_finished_info_re,
        parse_uuid_callback=parse_uuid_callback,
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        game_session_service=game_session_service,
    )
    if context is None:
        return

    answerable_message = _resolve_answerable_message(callback)
    _, challenge = context
    await answerable_message.answer(
        TEXTS_DE["msg.friend.challenge.info"],
        reply_markup=build_friend_challenge_finished_info_keyboard(
            challenge_id=str(challenge.challenge_id)
        ),
    )
    await callback.answer()
