from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aiogram.types import CallbackQuery

from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeLimitExceededError,
    FriendChallengeNotFoundError,
    FriendChallengePaymentRequiredError,
)

from .friend_series_flow_best3_render import notify_series_best3_opponent, send_series_best3_message
from .friend_series_flow_common import handle_series_flow_error


def _parse_series_best3_challenge_id(*, callback_data: str, pattern, parse_uuid_callback):
    return parse_uuid_callback(pattern=pattern, callback_data=callback_data)


async def _start_series_best3_duel(
    *,
    callback: CallbackQuery,
    challenge_id,
    session_local,
    user_onboarding_service,
    game_session_service,
) -> tuple[Any, Any]:
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        series_duel = await game_session_service.create_friend_challenge_best_of_three(
            session,
            initiator_user_id=snapshot.user_id,
            challenge_id=challenge_id,
            now_utc=datetime.now(timezone.utc),
            best_of=3,
        )
    return series_duel, snapshot


async def _run_friend_challenge_series_best3(
    callback: CallbackQuery, *, deps: dict[str, Any]
) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    message = callback.message
    if (
        challenge_id := _parse_series_best3_challenge_id(
            callback_data=callback.data,
            pattern=deps["friend_series_best3_re"],
            parse_uuid_callback=deps["parse_uuid_callback"],
        )
    ) is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    try:
        series_duel, snapshot = await _start_series_best3_duel(
            callback=callback,
            challenge_id=challenge_id,
            session_local=deps["session_local"],
            user_onboarding_service=deps["user_onboarding_service"],
            game_session_service=deps["game_session_service"],
        )
    except (
        FriendChallengePaymentRequiredError,
        FriendChallengeLimitExceededError,
        FriendChallengeNotFoundError,
        FriendChallengeAccessError,
    ) as exc:
        await handle_series_flow_error(callback=callback, message=message, exc=exc)
        return
    opponent_label = await deps["resolve_opponent_label"](
        challenge=series_duel,
        user_id=snapshot.user_id,
    )
    await send_series_best3_message(
        message=message,
        series_duel=series_duel,
        opponent_label=opponent_label,
        build_friend_plan_text=deps["build_friend_plan_text"],
        build_series_progress_text=deps["build_series_progress_text"],
    )
    await notify_series_best3_opponent(
        callback=callback,
        series_duel=series_duel,
        viewer_user_id=snapshot.user_id,
        resolve_opponent_label=deps["resolve_opponent_label"],
        friend_opponent_user_id=deps["friend_opponent_user_id"],
        notify_opponent=deps["notify_opponent"],
        build_friend_plan_text=deps["build_friend_plan_text"],
        build_series_progress_text=deps["build_series_progress_text"],
    )
    await callback.answer()


async def run_friend_challenge_series_best3(
    callback: CallbackQuery,
    *,
    friend_series_best3_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
    resolve_opponent_label,
    friend_opponent_user_id,
    notify_opponent,
    build_friend_plan_text,
    build_series_progress_text,
) -> None:
    await _run_friend_challenge_series_best3(
        callback,
        deps={
            "friend_series_best3_re": friend_series_best3_re,
            "parse_uuid_callback": parse_uuid_callback,
            "session_local": session_local,
            "user_onboarding_service": user_onboarding_service,
            "game_session_service": game_session_service,
            "resolve_opponent_label": resolve_opponent_label,
            "friend_opponent_user_id": friend_opponent_user_id,
            "notify_opponent": notify_opponent,
            "build_friend_plan_text": build_friend_plan_text,
            "build_series_progress_text": build_series_progress_text,
        },
    )


__all__ = ["run_friend_challenge_series_best3"]
