from __future__ import annotations

from functools import partial
from uuid import UUID

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.handlers import (
    gameplay_analytics,
    gameplay_callbacks,
    gameplay_daily_cup,
    gameplay_friend_challenge,
    gameplay_handler_bindings,
    gameplay_handler_stop,
    gameplay_helpers,
    gameplay_proof_cards,
    gameplay_tournaments,
    gameplay_views,
)
from app.bot.handlers.gameplay_flows import (
    answer_flow,
    daily_flow,
    daily_result_flow,
    friend_answer_flow,
    play_flow,
)
from app.bot.handlers.gameplay_friend_challenge import (  # noqa: F401
    handle_friend_challenge_create,
    handle_friend_challenge_create_selected,
    handle_friend_challenge_next,
    handle_friend_challenge_rematch,
    handle_friend_challenge_series_best3,
    handle_friend_challenge_series_next,
    handle_friend_challenge_share_result,
)
from app.bot.handlers.start_flow import _send_home_message
from app.bot.keyboards.friend_challenge import build_friend_challenge_share_url
from app.bot.texts.de import TEXTS_DE
from app.db.session import SessionLocal
from app.economy.offers.service import OfferLoggingError, OfferService
from app.economy.referrals.service import ReferralService
from app.game.sessions.service import GameSessionService
from app.services.channel_bonus import ChannelBonusService
from app.services.user_onboarding import UserOnboardingService

router = Router(name="gameplay")
EVENT_SOURCE_BOT = "BOT"
emit_analytics_event = gameplay_analytics.emit_analytics_event

ANSWER_RE, DAILY_RESULT_RE = gameplay_callbacks.ANSWER_RE, gameplay_callbacks.DAILY_RESULT_RE
gameplay_friend_challenge.register(router)
gameplay_tournaments.register(router)
gameplay_daily_cup.register(router)
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
_resolve_opponent_label = partial(
    gameplay_helpers._resolve_opponent_label,
    session_local=SessionLocal,
    users_repo=UserOnboardingService,
    format_user_label=_format_user_label,
)
_notify_opponent = partial(
    gameplay_helpers._notify_opponent,
    session_local=SessionLocal,
    users_repo=UserOnboardingService,
)
_build_friend_result_share_url = partial(
    gameplay_helpers._build_friend_result_share_url,
    share_cta_text=TEXTS_DE["msg.friend.challenge.proof.share.cta"],
    build_share_url=build_friend_challenge_share_url,
)
_send_friend_round_question = partial(
    play_flow.send_friend_round_question, build_question_text=_build_question_text
)


def _build_gameplay_flows() -> gameplay_handler_bindings.GameplayFlowBindings:
    return gameplay_handler_bindings.build_gameplay_flows(
        play_flow_start_mode=play_flow.start_mode,
        answer_flow_handle_answer=answer_flow.handle_answer,
        daily_result_flow_handle_daily_result_screen=daily_result_flow.handle_daily_result_screen,
        parse_answer_callback=gameplay_callbacks.parse_answer_callback,
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        game_session_service=GameSessionService,
        referral_service=ReferralService,
        channel_bonus_service=ChannelBonusService,
        offer_service=OfferService,
        offer_logging_error=OfferLoggingError,
        build_question_text=_build_question_text,
        emit_analytics_event=emit_analytics_event,
        event_source_bot=EVENT_SOURCE_BOT,
        continue_regular_mode_after_answer=play_flow.continue_regular_mode_after_answer,
        handle_daily_answer_branch=daily_flow.handle_daily_answer_branch,
        handle_friend_answer_branch=friend_answer_flow.handle_friend_answer_branch,
        resolve_opponent_label=_resolve_opponent_label,
        notify_opponent=_notify_opponent,
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


async def _answer_system_error(callback: CallbackQuery) -> None:
    await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)


async def _parse_daily_result_run_id(callback: CallbackQuery) -> UUID | None:
    if callback.data is None:
        await _answer_system_error(callback)
        return None
    daily_run_id = gameplay_callbacks.parse_uuid_callback(
        pattern=DAILY_RESULT_RE,
        callback_data=callback.data,
    )
    if daily_run_id is None:
        await _answer_system_error(callback)
        return None
    return daily_run_id


@router.callback_query(F.data.startswith("game:stop"))
async def handle_game_stop(callback: CallbackQuery) -> None:
    await gameplay_handler_stop.run_game_stop(
        callback,
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        game_session_service=GameSessionService,
        send_home_message=_send_home_message,
    )


@router.callback_query(F.data == "play")
async def handle_play(callback: CallbackQuery) -> None:
    await gameplay_handler_bindings.run_start_flow(
        callback,
        request=gameplay_handler_bindings.build_play_start_request(callback),
        start_mode=_build_gameplay_flows().start_mode,
    )


@router.callback_query(F.data == "daily_challenge")
async def handle_daily_challenge(callback: CallbackQuery) -> None:
    await gameplay_handler_bindings.run_start_flow(
        callback,
        request=gameplay_handler_bindings.build_daily_challenge_start_request(callback),
        start_mode=_build_gameplay_flows().start_mode,
    )


@router.callback_query(F.data.startswith("mode:"))
async def handle_mode(callback: CallbackQuery) -> None:
    request = await gameplay_handler_bindings.parse_mode_start_request(
        callback,
        parse_mode_code=gameplay_callbacks.parse_mode_code,
        answer_system_error=_answer_system_error,
    )
    if request is None:
        return
    await gameplay_handler_bindings.run_start_flow(
        callback,
        request=request,
        start_mode=_build_gameplay_flows().start_mode,
    )


@router.callback_query(F.data.regexp(ANSWER_RE))
async def handle_answer(callback: CallbackQuery) -> None:
    await _build_gameplay_flows().handle_answer(callback)


@router.callback_query(F.data.regexp(DAILY_RESULT_RE))
async def handle_daily_result(callback: CallbackQuery) -> None:
    daily_run_id = await _parse_daily_result_run_id(callback)
    if daily_run_id is None:
        return
    await _build_gameplay_flows().show_daily_result_screen(
        callback,
        daily_run_id=daily_run_id,
    )
