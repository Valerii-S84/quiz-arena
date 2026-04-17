from __future__ import annotations

from aiogram.types import CallbackQuery

from .friend_series_flow_next_runtime import run_friend_challenge_series_next


async def handle_friend_challenge_series_next(
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
    await run_friend_challenge_series_next(
        callback,
        friend_series_next_re=friend_series_next_re,
        parse_uuid_callback=parse_uuid_callback,
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        game_session_service=game_session_service,
        resolve_opponent_label=resolve_opponent_label,
        friend_opponent_user_id=friend_opponent_user_id,
        notify_opponent=notify_opponent,
        build_friend_plan_text=build_friend_plan_text,
        build_series_progress_text=build_series_progress_text,
    )


__all__ = ["handle_friend_challenge_series_next"]
