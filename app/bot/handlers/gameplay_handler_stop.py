from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast
from uuid import UUID

from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

from app.bot.handlers import gameplay_callbacks
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import SessionNotFoundError, TournamentSessionStopNotAllowedError


@dataclass(frozen=True, slots=True)
class GameStopRequest:
    message: Message
    session_id: UUID | None
    telegram_user: TelegramUser | None


async def _answer_system_error(callback: CallbackQuery) -> None:
    await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)


async def parse_game_stop_request(callback: CallbackQuery) -> GameStopRequest | None:
    if callback.message is None or callback.data is None:
        await _answer_system_error(callback)
        return None
    if callback.data == "game:stop":
        return GameStopRequest(
            message=cast(Message, callback.message),
            session_id=None,
            telegram_user=None,
        )
    if callback.from_user is None:
        await _answer_system_error(callback)
        return None
    session_id = gameplay_callbacks.parse_stop_callback(callback.data)
    if session_id is None:
        await _answer_system_error(callback)
        return None
    return GameStopRequest(
        message=cast(Message, callback.message),
        session_id=session_id,
        telegram_user=callback.from_user,
    )


async def abandon_requested_game_session(
    callback: CallbackQuery,
    *,
    request: GameStopRequest,
    session_local,
    user_onboarding_service,
    game_session_service,
) -> bool:
    if request.session_id is None or request.telegram_user is None:
        return True

    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=request.telegram_user,
        )
        try:
            await game_session_service.abandon_session(
                session,
                user_id=snapshot.user_id,
                session_id=request.session_id,
                now_utc=now_utc,
            )
        except TournamentSessionStopNotAllowedError:
            await _answer_system_error(callback)
            return False
        except SessionNotFoundError:
            return True
    return True


async def run_game_stop(
    callback: CallbackQuery,
    *,
    session_local,
    user_onboarding_service,
    game_session_service,
    send_home_message,
) -> None:
    request = await parse_game_stop_request(callback)
    if request is None:
        return
    if not await abandon_requested_game_session(
        callback,
        request=request,
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        game_session_service=game_session_service,
    ):
        return
    await send_home_message(request.message, text=TEXTS_DE["msg.game.stopped"])
    await callback.answer()
