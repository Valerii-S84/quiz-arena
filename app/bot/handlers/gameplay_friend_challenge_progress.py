from __future__ import annotations

from aiogram.types import CallbackQuery

from app.bot.handlers import gameplay_callbacks
from app.bot.handlers.gameplay_flows import (
    friend_challenge_flow,
    friend_next_flow,
    friend_series_flow,
    proof_card_flow,
)
from app.bot.handlers.gameplay_friend_challenge_context import get_gameplay_module


async def handle_friend_challenge_rematch(callback: CallbackQuery) -> None:
    gameplay = get_gameplay_module()
    await friend_challenge_flow.handle_friend_challenge_rematch(
        callback,
        friend_rematch_re=gameplay_callbacks.FRIEND_REMATCH_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=gameplay.SessionLocal,
        user_onboarding_service=gameplay.UserOnboardingService,
        game_session_service=gameplay.GameSessionService,
        resolve_opponent_label=gameplay._resolve_opponent_label,
        friend_opponent_user_id=gameplay._friend_opponent_user_id,
        notify_opponent=gameplay._notify_opponent,
        build_friend_plan_text=gameplay._build_friend_plan_text,
        build_friend_ttl_text=gameplay._build_friend_ttl_text,
    )


async def handle_friend_challenge_series_best3(callback: CallbackQuery) -> None:
    gameplay = get_gameplay_module()
    await friend_series_flow.handle_friend_challenge_series_best3(
        callback,
        friend_series_best3_re=gameplay_callbacks.FRIEND_SERIES_BEST3_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=gameplay.SessionLocal,
        user_onboarding_service=gameplay.UserOnboardingService,
        game_session_service=gameplay.GameSessionService,
        resolve_opponent_label=gameplay._resolve_opponent_label,
        friend_opponent_user_id=gameplay._friend_opponent_user_id,
        notify_opponent=gameplay._notify_opponent,
        build_friend_plan_text=gameplay._build_friend_plan_text,
        build_series_progress_text=gameplay._build_series_progress_text,
    )


async def handle_friend_challenge_series_next(callback: CallbackQuery) -> None:
    gameplay = get_gameplay_module()
    await friend_series_flow.handle_friend_challenge_series_next(
        callback,
        friend_series_next_re=gameplay_callbacks.FRIEND_SERIES_NEXT_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=gameplay.SessionLocal,
        user_onboarding_service=gameplay.UserOnboardingService,
        game_session_service=gameplay.GameSessionService,
        resolve_opponent_label=gameplay._resolve_opponent_label,
        friend_opponent_user_id=gameplay._friend_opponent_user_id,
        notify_opponent=gameplay._notify_opponent,
        build_friend_plan_text=gameplay._build_friend_plan_text,
        build_series_progress_text=gameplay._build_series_progress_text,
    )


async def handle_friend_challenge_share_result(callback: CallbackQuery) -> None:
    gameplay = get_gameplay_module()
    await proof_card_flow.handle_friend_challenge_share_result(
        callback,
        friend_share_result_re=gameplay_callbacks.FRIEND_SHARE_RESULT_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=gameplay.SessionLocal,
        user_onboarding_service=gameplay.UserOnboardingService,
        game_session_service=gameplay.GameSessionService,
        resolve_opponent_label=gameplay._resolve_opponent_label,
        build_friend_proof_card_text=gameplay._build_friend_proof_card_text,
        build_friend_result_share_url=gameplay._build_friend_result_share_url,
        emit_analytics_event=gameplay.emit_analytics_event,
        event_source_bot=gameplay.EVENT_SOURCE_BOT,
    )


async def handle_friend_challenge_next(callback: CallbackQuery) -> None:
    gameplay = get_gameplay_module()
    await friend_next_flow.handle_friend_challenge_next(
        callback,
        friend_next_re=gameplay_callbacks.FRIEND_NEXT_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=gameplay.SessionLocal,
        user_onboarding_service=gameplay.UserOnboardingService,
        game_session_service=gameplay.GameSessionService,
        resolve_opponent_label=gameplay._resolve_opponent_label,
        build_friend_score_text=gameplay._build_friend_score_text,
        build_friend_ttl_text=gameplay._build_friend_ttl_text,
        send_friend_round_question=gameplay._send_friend_round_question,
    )
