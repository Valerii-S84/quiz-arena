from __future__ import annotations

from aiogram.types import CallbackQuery

from .friend_series_flow_best3_runtime import run_friend_challenge_series_best3


async def handle_friend_challenge_series_best3(
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
    await run_friend_challenge_series_best3(
        callback,
        friend_series_best3_re=friend_series_best3_re,
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


__all__ = ["handle_friend_challenge_series_best3"]
