from __future__ import annotations

from functools import partial
from typing import Any, cast

from app.bot.handlers.gameplay_handler_answer_bindings import build_answer_flow_binding

__all__ = [
    "build_start_mode_binding_kwargs",
    "build_start_mode_flow_binding",
    "build_answer_flow_binding",
    "build_daily_result_binding_kwargs",
    "build_daily_result_flow_binding",
]


def build_start_mode_binding_kwargs(
    *,
    session_local,
    user_onboarding_service,
    game_session_service,
    offer_service,
    offer_logging_error,
    channel_bonus_service,
    build_question_text,
) -> dict[str, Any]:
    return {
        "session_local": session_local,
        "user_onboarding_service": user_onboarding_service,
        "game_session_service": game_session_service,
        "offer_service": offer_service,
        "offer_logging_error": offer_logging_error,
        "channel_bonus_service": channel_bonus_service,
        "build_question_text": build_question_text,
    }


def build_start_mode_flow_binding(
    *,
    play_flow_start_mode,
    session_local,
    user_onboarding_service,
    game_session_service,
    offer_service,
    offer_logging_error,
    channel_bonus_service,
    build_question_text,
) -> Any:
    return cast(
        Any,
        partial(
            play_flow_start_mode,
            **build_start_mode_binding_kwargs(
                session_local=session_local,
                user_onboarding_service=user_onboarding_service,
                game_session_service=game_session_service,
                offer_service=offer_service,
                offer_logging_error=offer_logging_error,
                channel_bonus_service=channel_bonus_service,
                build_question_text=build_question_text,
            ),
        ),
    )


def build_daily_result_binding_kwargs(
    *,
    session_local,
    user_onboarding_service,
    game_session_service,
) -> dict[str, Any]:
    return {
        "session_local": session_local,
        "user_onboarding_service": user_onboarding_service,
        "game_session_service": game_session_service,
    }


def build_daily_result_flow_binding(
    *,
    daily_result_flow_handle_daily_result_screen,
    session_local,
    user_onboarding_service,
    game_session_service,
) -> Any:
    return cast(
        Any,
        partial(
            daily_result_flow_handle_daily_result_screen,
            **build_daily_result_binding_kwargs(
                session_local=session_local,
                user_onboarding_service=user_onboarding_service,
                game_session_service=game_session_service,
            ),
        ),
    )
