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
from .friend_series_flow_common import build_series_reply_markup, handle_series_flow_error


def _build_series_start_text(
    *,
    series_duel: Any,
    opponent_label: str,
    build_friend_plan_text,
    build_series_progress_text,
) -> str:
    return "\n".join(
        [
            TEXTS_DE["msg.friend.challenge.series.started"].format(opponent_label=opponent_label),
            build_friend_plan_text(total_rounds=series_duel.total_rounds),
            build_series_progress_text(
                game_no=series_duel.series_game_number,
                best_of=series_duel.series_best_of,
                my_wins=0,
                opponent_wins=0,
                opponent_label=opponent_label,
            ),
        ]
    )


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


async def _send_series_start_message(
    *,
    message: Any,
    series_duel: Any,
    opponent_label: str,
    build_friend_plan_text,
    build_series_progress_text,
) -> None:
    await message.answer(
        _build_series_start_text(
            series_duel=series_duel,
            opponent_label=opponent_label,
            build_friend_plan_text=build_friend_plan_text,
            build_series_progress_text=build_series_progress_text,
        ),
        reply_markup=build_series_reply_markup(challenge_id=str(series_duel.challenge_id)),
    )


async def _notify_series_start_opponent(
    *,
    callback: CallbackQuery,
    series_duel: Any,
    viewer_user_id: int,
    resolve_opponent_label,
    friend_opponent_user_id,
    notify_opponent,
    build_friend_plan_text,
    build_series_progress_text,
) -> None:
    opponent_user_id = friend_opponent_user_id(challenge=series_duel, user_id=viewer_user_id)
    if opponent_user_id is None:
        return
    opponent_label = await resolve_opponent_label(challenge=series_duel, user_id=opponent_user_id)
    await notify_opponent(
        callback,
        opponent_user_id=opponent_user_id,
        text=_build_series_start_text(
            series_duel=series_duel,
            opponent_label=opponent_label,
            build_friend_plan_text=build_friend_plan_text,
            build_series_progress_text=build_series_progress_text,
        ),
        reply_markup=build_series_reply_markup(challenge_id=str(series_duel.challenge_id)),
    )


async def _run_friend_challenge_series_best3(callback: CallbackQuery, *, deps: dict[str, Any]) -> None:
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
    await _send_series_start_message(
        message=message,
        series_duel=series_duel,
        opponent_label=opponent_label,
        build_friend_plan_text=deps["build_friend_plan_text"],
        build_series_progress_text=deps["build_series_progress_text"],
    )
    await _notify_series_start_opponent(
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
