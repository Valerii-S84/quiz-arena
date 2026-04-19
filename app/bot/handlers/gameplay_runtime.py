from __future__ import annotations

from functools import partial
from uuid import UUID

from aiogram.types import CallbackQuery

from app.bot.handlers import (
    gameplay_analytics,
    gameplay_callbacks,
    gameplay_handler_bindings,
    gameplay_helpers,
    gameplay_proof_cards,
    gameplay_views,
)
from app.bot.handlers.gameplay_flows import (
    answer_flow,
    daily_flow,
    daily_result_flow,
    friend_answer_flow,
    play_flow,
)
from app.bot.keyboards.friend_challenge import build_friend_challenge_share_url
from app.bot.texts.de import TEXTS_DE

EVENT_SOURCE_BOT = "BOT"
emit_analytics_event = gameplay_analytics.emit_analytics_event

_format_user_label = gameplay_views._format_user_label
_build_friend_plan_text = gameplay_views._build_friend_plan_text
_build_question_text = gameplay_views._build_question_text
_build_friend_score_text = gameplay_views._build_friend_score_text
_build_friend_finish_text = gameplay_views._build_friend_finish_text
_build_public_badge_label = gameplay_views._build_public_badge_label
_build_series_progress_text = gameplay_views._build_series_progress_text
_build_friend_proof_card_text = gameplay_views._build_friend_proof_card_text
_build_friend_ttl_text = gameplay_views._build_friend_ttl_text
_friend_opponent_user_id = gameplay_helpers._friend_opponent_user_id
_build_friend_invite_link = gameplay_helpers._build_friend_invite_link
_build_friend_result_share_url = partial(
    gameplay_helpers._build_friend_result_share_url,
    share_cta_text=TEXTS_DE["msg.friend.challenge.proof.share.cta"],
    build_share_url=build_friend_challenge_share_url,
)
_send_friend_round_question = partial(
    play_flow.send_friend_round_question,
    build_question_text=_build_question_text,
)


def build_gameplay_flows(
    session_local,
    user_onboarding_service,
    game_session_service,
    referral_service,
    channel_bonus_service,
    offer_service,
    offer_logging_error,
    build_question_text,
    emit_analytics_event,
    resolve_opponent_label,
    notify_opponent,
) -> gameplay_handler_bindings.GameplayFlowBindings:
    return gameplay_handler_bindings.build_gameplay_flows(
        play_flow_start_mode=play_flow.start_mode,
        answer_flow_handle_answer=answer_flow.handle_answer,
        daily_result_flow_handle_daily_result_screen=daily_result_flow.handle_daily_result_screen,
        parse_answer_callback=gameplay_callbacks.parse_answer_callback,
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        game_session_service=game_session_service,
        referral_service=referral_service,
        channel_bonus_service=channel_bonus_service,
        offer_service=offer_service,
        offer_logging_error=offer_logging_error,
        build_question_text=build_question_text,
        emit_analytics_event=emit_analytics_event,
        event_source_bot=EVENT_SOURCE_BOT,
        continue_regular_mode_after_answer=play_flow.continue_regular_mode_after_answer,
        handle_daily_answer_branch=daily_flow.handle_daily_answer_branch,
        handle_friend_answer_branch=friend_answer_flow.handle_friend_answer_branch,
        resolve_opponent_label=resolve_opponent_label,
        notify_opponent=notify_opponent,
        friend_opponent_user_id=_friend_opponent_user_id,
        build_friend_score_text=_build_friend_score_text,
        build_friend_ttl_text=_build_friend_ttl_text,
        build_friend_finish_text=_build_friend_finish_text,
        build_public_badge_label=_build_public_badge_label,
        build_friend_proof_card_text=_build_friend_proof_card_text,
        enqueue_friend_challenge_proof_cards=gameplay_proof_cards.enqueue_duel_proof_cards,
        build_series_progress_text=_build_series_progress_text,
        send_friend_round_question=_send_friend_round_question,
    )


async def answer_system_error(callback: CallbackQuery) -> None:
    await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)


async def parse_daily_result_run_id(callback: CallbackQuery) -> UUID | None:
    if callback.data is None:
        await answer_system_error(callback)
        return None
    daily_run_id = gameplay_callbacks.parse_uuid_callback(
        pattern=gameplay_callbacks.DAILY_RESULT_RE,
        callback_data=callback.data,
    )
    if daily_run_id is None:
        await answer_system_error(callback)
        return None
    return daily_run_id
