from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram.types import CallbackQuery

from app.bot.handlers import gameplay_handler_flow_bindings


@dataclass(frozen=True, slots=True)
class GameplayFlowBindings:
    start_mode: Any
    handle_answer: Any
    show_daily_result_screen: Any


@dataclass(frozen=True, slots=True)
class StartFlowRequest:
    mode_code: str
    source: str
    idempotency_key: str


def build_gameplay_flows(
    *,
    play_flow_start_mode,
    answer_flow_handle_answer,
    daily_result_flow_handle_daily_result_screen,
    parse_answer_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
    referral_service,
    channel_bonus_service,
    offer_service,
    offer_logging_error,
    build_question_text,
    emit_analytics_event,
    event_source_bot,
    continue_regular_mode_after_answer,
    handle_daily_answer_branch,
    handle_friend_answer_branch,
    resolve_opponent_label,
    notify_opponent,
    friend_opponent_user_id,
    build_friend_score_text,
    build_friend_ttl_text,
    build_friend_finish_text,
    build_public_badge_label,
    build_friend_proof_card_text,
    enqueue_friend_challenge_proof_cards,
    build_series_progress_text,
    send_friend_round_question,
) -> GameplayFlowBindings:
    return GameplayFlowBindings(
        start_mode=gameplay_handler_flow_bindings.build_start_mode_flow_binding(
            play_flow_start_mode=play_flow_start_mode,
            session_local=session_local,
            user_onboarding_service=user_onboarding_service,
            game_session_service=game_session_service,
            offer_service=offer_service,
            offer_logging_error=offer_logging_error,
            channel_bonus_service=channel_bonus_service,
            build_question_text=build_question_text,
        ),
        handle_answer=gameplay_handler_flow_bindings.build_answer_flow_binding(
            answer_flow_handle_answer=answer_flow_handle_answer,
            parse_answer_callback=parse_answer_callback,
            session_local=session_local,
            user_onboarding_service=user_onboarding_service,
            game_session_service=game_session_service,
            referral_service=referral_service,
            channel_bonus_service=channel_bonus_service,
            offer_service=offer_service,
            offer_logging_error=offer_logging_error,
            build_question_text=build_question_text,
            emit_analytics_event=emit_analytics_event,
            event_source_bot=event_source_bot,
            continue_regular_mode_after_answer=continue_regular_mode_after_answer,
            handle_daily_answer_branch=handle_daily_answer_branch,
            handle_friend_answer_branch=handle_friend_answer_branch,
            resolve_opponent_label=resolve_opponent_label,
            notify_opponent=notify_opponent,
            friend_opponent_user_id=friend_opponent_user_id,
            build_friend_score_text=build_friend_score_text,
            build_friend_ttl_text=build_friend_ttl_text,
            build_friend_finish_text=build_friend_finish_text,
            build_public_badge_label=build_public_badge_label,
            build_friend_proof_card_text=build_friend_proof_card_text,
            enqueue_friend_challenge_proof_cards=enqueue_friend_challenge_proof_cards,
            build_series_progress_text=build_series_progress_text,
            send_friend_round_question=send_friend_round_question,
        ),
        show_daily_result_screen=gameplay_handler_flow_bindings.build_daily_result_flow_binding(
            daily_result_flow_handle_daily_result_screen=daily_result_flow_handle_daily_result_screen,
            session_local=session_local,
            user_onboarding_service=user_onboarding_service,
            game_session_service=game_session_service,
        ),
    )


def build_start_flow_request(
    *,
    mode_code: str,
    source: str,
    idempotency_key: str,
) -> StartFlowRequest:
    return StartFlowRequest(
        mode_code=mode_code,
        source=source,
        idempotency_key=idempotency_key,
    )


def build_play_start_request(callback: CallbackQuery) -> StartFlowRequest:
    return build_start_flow_request(
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        idempotency_key=f"start:play:{callback.id}",
    )


def build_daily_challenge_start_request(callback: CallbackQuery) -> StartFlowRequest:
    return build_start_flow_request(
        mode_code="DAILY_CHALLENGE",
        source="DAILY_CHALLENGE",
        idempotency_key=f"start:daily:{callback.id}",
    )


async def parse_mode_start_request(
    callback: CallbackQuery,
    *,
    parse_mode_code,
    answer_system_error,
) -> StartFlowRequest | None:
    if callback.data is None:
        await answer_system_error(callback)
        return None
    mode_code = parse_mode_code(callback.data)
    return build_start_flow_request(
        mode_code=mode_code,
        source="MENU",
        idempotency_key=f"start:mode:{mode_code}:{callback.id}",
    )


async def run_start_flow(
    callback: CallbackQuery,
    *,
    request: StartFlowRequest,
    start_mode,
) -> None:
    await start_mode(
        callback,
        mode_code=request.mode_code,
        source=request.source,
        idempotency_key=request.idempotency_key,
    )
