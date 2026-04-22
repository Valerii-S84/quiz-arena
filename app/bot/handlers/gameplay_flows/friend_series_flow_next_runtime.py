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

from .friend_series_flow_common import handle_series_flow_error
from .friend_series_flow_next_render import notify_series_next_opponent, send_series_next_message


def _parse_series_next_challenge_id(*, callback_data: str, pattern, parse_uuid_callback):
    return parse_uuid_callback(pattern=pattern, callback_data=callback_data)


async def _start_series_next_duel(
    *,
    callback: CallbackQuery,
    challenge_id,
    session_local,
    user_onboarding_service,
    game_session_service,
) -> tuple[Any, Any, tuple[int, int, int, int]]:
    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        next_duel = await game_session_service.create_friend_challenge_series_next_game(
            session,
            initiator_user_id=snapshot.user_id,
            challenge_id=challenge_id,
            now_utc=now_utc,
        )
        score = await game_session_service.get_friend_series_score_for_user(
            session,
            user_id=snapshot.user_id,
            challenge_id=next_duel.challenge_id,
            now_utc=now_utc,
        )
    return next_duel, snapshot, score


async def _load_series_next_context(
    *,
    callback: CallbackQuery,
    message: Any,
    challenge_id,
    session_local,
    user_onboarding_service,
    game_session_service,
) -> tuple[Any, Any, tuple[int, int, int, int]] | None:
    try:
        return await _start_series_next_duel(
            callback=callback,
            challenge_id=challenge_id,
            session_local=session_local,
            user_onboarding_service=user_onboarding_service,
            game_session_service=game_session_service,
        )
    except (
        FriendChallengePaymentRequiredError,
        FriendChallengeLimitExceededError,
        FriendChallengeNotFoundError,
        FriendChallengeAccessError,
    ) as exc:
        await handle_series_flow_error(callback=callback, message=message, exc=exc)
        return None


async def _run_friend_challenge_series_next(
    callback: CallbackQuery, *, deps: dict[str, Any]
) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    message = callback.message
    if (
        challenge_id := _parse_series_next_challenge_id(
            callback_data=callback.data,
            pattern=deps["friend_series_next_re"],
            parse_uuid_callback=deps["parse_uuid_callback"],
        )
    ) is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    context = await _load_series_next_context(
        callback=callback,
        message=message,
        challenge_id=challenge_id,
        session_local=deps["session_local"],
        user_onboarding_service=deps["user_onboarding_service"],
        game_session_service=deps["game_session_service"],
    )
    if context is None:
        return
    next_duel, snapshot, score = context
    my_wins, opponent_wins, game_no, best_of = score
    opponent_label = await deps["resolve_opponent_label"](
        challenge=next_duel, user_id=snapshot.user_id
    )
    await send_series_next_message(
        message=message,
        next_duel=next_duel,
        opponent_label=opponent_label,
        game_no=game_no,
        best_of=best_of,
        my_wins=my_wins,
        opponent_wins=opponent_wins,
        build_friend_plan_text=deps["build_friend_plan_text"],
        build_series_progress_text=deps["build_series_progress_text"],
    )
    await notify_series_next_opponent(
        callback=callback,
        next_duel=next_duel,
        viewer_user_id=snapshot.user_id,
        game_no=game_no,
        best_of=best_of,
        my_wins=my_wins,
        opponent_wins=opponent_wins,
        resolve_opponent_label=deps["resolve_opponent_label"],
        friend_opponent_user_id=deps["friend_opponent_user_id"],
        notify_opponent=deps["notify_opponent"],
        build_friend_plan_text=deps["build_friend_plan_text"],
        build_series_progress_text=deps["build_series_progress_text"],
    )
    await callback.answer()


async def run_friend_challenge_series_next(
    callback: CallbackQuery,
    *,
    friend_series_next_re,
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
    await _run_friend_challenge_series_next(
        callback,
        deps={
            "friend_series_next_re": friend_series_next_re,
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


__all__ = ["run_friend_challenge_series_next"]
