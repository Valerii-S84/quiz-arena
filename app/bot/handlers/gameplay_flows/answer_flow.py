from __future__ import annotations

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows import answer_flow_runtime
from app.bot.handlers.gameplay_flows.answer_flow_runtime_context import build_answer_flow_deps
from app.bot.handlers.start_flow import _send_home_message


async def handle_answer(
    callback: CallbackQuery,
    *,
    parse_answer_callback,
    session_local,
    user_onboarding_service,
    referral_service,
    channel_bonus_service,
    game_session_service,
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
) -> None:
    await answer_flow_runtime.run_answer_flow(
        callback,
        parse_answer_callback=parse_answer_callback,
        deps=build_answer_flow_deps(
            session_local=session_local,
            user_onboarding_service=user_onboarding_service,
            referral_service=referral_service,
            channel_bonus_service=channel_bonus_service,
            game_session_service=game_session_service,
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
        send_home_message=_send_home_message,
    )
