from __future__ import annotations

from datetime import datetime, timezone
from functools import partial
from typing import cast

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.bot.handlers import (
    gameplay_callbacks,
    gameplay_friend_challenge,
    gameplay_helpers,
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
from app.economy.offers.constants import TRG_LOCKED_MODE_CLICK
from app.economy.offers.service import OfferLoggingError, OfferService
from app.game.sessions.errors import SessionNotFoundError
from app.game.sessions.service import GameSessionService
from app.services.user_onboarding import UserOnboardingService

router = Router(name="gameplay")
EVENT_SOURCE_BOT = "BOT"

ANSWER_RE = gameplay_callbacks.ANSWER_RE
DAILY_RESULT_RE = gameplay_callbacks.DAILY_RESULT_RE

gameplay_friend_challenge.register(router)

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


def _session_deps() -> dict[str, object]:
    return {
        "session_local": SessionLocal,
        "user_onboarding_service": UserOnboardingService,
        "game_session_service": GameSessionService,
    }


async def emit_analytics_event(*args, **kwargs):
    from app.core.analytics_events import emit_analytics_event as _emit_analytics_event

    await _emit_analytics_event(*args, **kwargs)


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
_start_mode = partial(
    play_flow.start_mode,
    **_session_deps(),
    offer_service=OfferService,
    offer_logging_error=OfferLoggingError,
    trg_locked_mode_click=TRG_LOCKED_MODE_CLICK,
    build_question_text=_build_question_text,
)
_send_friend_round_question = partial(
    play_flow.send_friend_round_question,
    build_question_text=_build_question_text,
)


@router.callback_query(F.data.startswith("game:stop"))
async def handle_game_stop(callback: CallbackQuery) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    if callback.data != "game:stop":
        if callback.from_user is None:
            await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
            return
        session_id = gameplay_callbacks.parse_stop_callback(callback.data)
        if session_id is None:
            await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
            return
        now_utc = datetime.now(timezone.utc)
        async with SessionLocal.begin() as session:
            snapshot = await UserOnboardingService.ensure_home_snapshot(
                session,
                telegram_user=callback.from_user,
            )
            try:
                await GameSessionService.abandon_session(
                    session,
                    user_id=snapshot.user_id,
                    session_id=session_id,
                    now_utc=now_utc,
                )
            except SessionNotFoundError:
                pass
    await _send_home_message(cast(Message, callback.message), text=TEXTS_DE["msg.game.stopped"])
    await callback.answer()


@router.callback_query(F.data == "play")
async def handle_play(callback: CallbackQuery) -> None:
    await _start_mode(
        callback,
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        idempotency_key=f"start:play:{callback.id}",
    )


@router.callback_query(F.data == "daily_challenge")
async def handle_daily_challenge(callback: CallbackQuery) -> None:
    await _start_mode(
        callback,
        mode_code="DAILY_CHALLENGE",
        source="DAILY_CHALLENGE",
        idempotency_key=f"start:daily:{callback.id}",
    )


@router.callback_query(F.data.startswith("mode:"))
async def handle_mode(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    mode_code = gameplay_callbacks.parse_mode_code(callback.data)
    await _start_mode(
        callback,
        mode_code=mode_code,
        source="MENU",
        idempotency_key=f"start:mode:{mode_code}:{callback.id}",
    )


@router.callback_query(F.data.regexp(ANSWER_RE))
async def handle_answer(callback: CallbackQuery) -> None:
    await answer_flow.handle_answer(
        callback,
        parse_answer_callback=gameplay_callbacks.parse_answer_callback,
        **_session_deps(),
        offer_service=OfferService,
        offer_logging_error=OfferLoggingError,
        build_question_text=_build_question_text,
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
        build_series_progress_text=_build_series_progress_text,
        send_friend_round_question=_send_friend_round_question,
    )


@router.callback_query(F.data.regexp(DAILY_RESULT_RE))
async def handle_daily_result(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    daily_run_id = gameplay_callbacks.parse_uuid_callback(
        pattern=DAILY_RESULT_RE,
        callback_data=callback.data,
    )
    if daily_run_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await daily_result_flow.handle_daily_result_screen(
        callback,
        daily_run_id=daily_run_id,
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        game_session_service=GameSessionService,
    )
