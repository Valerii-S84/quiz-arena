from __future__ import annotations

from aiogram import F, Router

from app.bot.handlers import (
    gameplay_callbacks,
    gameplay_daily_cup,
    gameplay_friend_challenge,
    gameplay_handler_bindings,
    gameplay_handler_stop,
    gameplay_helpers,
)
from app.bot.handlers import gameplay_proof_cards as _gameplay_proof_cards
from app.bot.handlers import gameplay_runtime, gameplay_tournaments
from app.bot.handlers.gameplay_flows import daily_flow as _daily_flow
from app.bot.handlers.gameplay_flows import daily_result_flow as _daily_result_flow
from app.bot.handlers.gameplay_flows import play_flow as _play_flow
from app.bot.handlers.gameplay_friend_challenge import (  # noqa: F401
    handle_friend_challenge_create,
    handle_friend_challenge_create_selected,
    handle_friend_challenge_finished_info,
    handle_friend_challenge_finished_show,
    handle_friend_challenge_next,
    handle_friend_challenge_onboarding_info,
    handle_friend_challenge_onboarding_show,
    handle_friend_challenge_rematch,
    handle_friend_challenge_series_best3,
    handle_friend_challenge_series_next,
    handle_friend_challenge_share_result,
)
from app.bot.handlers.start_flow import _send_home_message
from app.db.session import SessionLocal
from app.economy.offers.service import OfferLoggingError as _OLE
from app.economy.offers.service import OfferService as _OS
from app.economy.referrals.service import ReferralService as _ReferralService
from app.game.sessions.service import GameSessionService
from app.services.channel_bonus import ChannelBonusService as _ChannelBonusService
from app.services.user_onboarding import UserOnboardingService

router = Router(name="gameplay")

ANSWER_RE, DAILY_RESULT_RE = gameplay_callbacks.ANSWER_RE, gameplay_callbacks.DAILY_RESULT_RE
gameplay_friend_challenge.register(router)
gameplay_tournaments.register(router)
gameplay_daily_cup.register(router)
play_flow, daily_flow, daily_result_flow = _play_flow, _daily_flow, _daily_result_flow
gameplay_proof_cards = _gameplay_proof_cards
OfferService, OfferLoggingError = _OS, _OLE
ReferralService, ChannelBonusService = _ReferralService, _ChannelBonusService
(
    EVENT_SOURCE_BOT,
    emit_analytics_event,
    _format_user_label,
    _build_friend_plan_text,
    _build_question_text,
    _build_friend_score_text,
    _build_friend_finish_text,
    _build_public_badge_label,
    _build_series_progress_text,
    _build_friend_proof_card_text,
    _build_friend_ttl_text,
    _friend_opponent_user_id,
    _build_friend_invite_link,
    _build_friend_result_share_url,
    _send_friend_round_question,
    answer_system_error,
    parse_daily_result_run_id,
) = (
    gameplay_runtime.EVENT_SOURCE_BOT,
    gameplay_runtime.emit_analytics_event,
    gameplay_runtime._format_user_label,
    gameplay_runtime._build_friend_plan_text,
    gameplay_runtime._build_question_text,
    gameplay_runtime._build_friend_score_text,
    gameplay_runtime._build_friend_finish_text,
    gameplay_runtime._build_public_badge_label,
    gameplay_runtime._build_series_progress_text,
    gameplay_runtime._build_friend_proof_card_text,
    gameplay_runtime._build_friend_ttl_text,
    gameplay_runtime._friend_opponent_user_id,
    gameplay_runtime._build_friend_invite_link,
    gameplay_runtime._build_friend_result_share_url,
    gameplay_runtime._send_friend_round_question,
    gameplay_runtime.answer_system_error,
    gameplay_runtime.parse_daily_result_run_id,
)


def _resolve_opponent_label(*, challenge, user_id: int):
    return gameplay_helpers._resolve_opponent_label(
        challenge=challenge,
        user_id=user_id,
        session_local=SessionLocal,
        users_repo=UserOnboardingService,
        format_user_label=_format_user_label,
    )


def _notify_opponent(callback, *, opponent_user_id, text, reply_markup=None):
    return gameplay_helpers._notify_opponent(
        callback,
        opponent_user_id=opponent_user_id,
        text=text,
        reply_markup=reply_markup,
        session_local=SessionLocal,
        users_repo=UserOnboardingService,
    )


def build_gameplay_flows() -> gameplay_handler_bindings.GameplayFlowBindings:
    return gameplay_runtime.build_gameplay_flows(
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        game_session_service=GameSessionService,
        referral_service=ReferralService,
        channel_bonus_service=ChannelBonusService,
        offer_service=OfferService,
        offer_logging_error=OfferLoggingError,
        build_question_text=_build_question_text,
        emit_analytics_event=emit_analytics_event,
        resolve_opponent_label=_resolve_opponent_label,
        notify_opponent=_notify_opponent,
    )


@router.callback_query(F.data.startswith("game:stop"))
async def handle_game_stop(callback) -> None:
    await gameplay_handler_stop.run_game_stop(
        callback,
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        game_session_service=GameSessionService,
        send_home_message=_send_home_message,
    )


@router.callback_query(F.data == "play")
async def handle_play(callback) -> None:
    await gameplay_handler_bindings.run_start_flow(
        callback,
        request=gameplay_handler_bindings.build_play_start_request(callback),
        start_mode=build_gameplay_flows().start_mode,
    )


@router.callback_query(F.data == "daily_challenge")
async def handle_daily_challenge(callback) -> None:
    await gameplay_handler_bindings.run_start_flow(
        callback,
        request=gameplay_handler_bindings.build_daily_challenge_start_request(callback),
        start_mode=build_gameplay_flows().start_mode,
    )


@router.callback_query(F.data.startswith("mode:"))
async def handle_mode(callback) -> None:
    request = await gameplay_handler_bindings.parse_mode_start_request(
        callback,
        parse_mode_code=gameplay_callbacks.parse_mode_code,
        answer_system_error=answer_system_error,
    )
    if request is None:
        return
    await gameplay_handler_bindings.run_start_flow(
        callback,
        request=request,
        start_mode=build_gameplay_flows().start_mode,
    )


@router.callback_query(F.data.regexp(ANSWER_RE))
async def handle_answer(callback) -> None:
    await build_gameplay_flows().handle_answer(callback)


@router.callback_query(F.data.regexp(DAILY_RESULT_RE))
async def handle_daily_result(callback) -> None:
    daily_run_id = await parse_daily_result_run_id(callback)
    if daily_run_id is None:
        return
    await build_gameplay_flows().show_daily_result_screen(
        callback,
        daily_run_id=daily_run_id,
    )
