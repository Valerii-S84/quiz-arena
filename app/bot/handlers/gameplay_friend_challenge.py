from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.handlers import gameplay_callbacks
from app.bot.handlers.gameplay_flows import (
    friend_challenge_flow,
    friend_next_flow,
    friend_series_flow,
    proof_card_flow,
)
from app.bot.keyboards.friend_challenge import build_friend_challenge_create_keyboard
from app.bot.texts.de import TEXTS_DE


def _gameplay():
    from app.bot.handlers import gameplay

    return gameplay


def register(router: Router) -> None:
    router.callback_query(F.data == "friend:challenge:create")(handle_friend_challenge_create)
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_CREATE_RE))(
        handle_friend_challenge_create_selected
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_REMATCH_RE))(
        handle_friend_challenge_rematch
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_SERIES_BEST3_RE))(
        handle_friend_challenge_series_best3
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_SERIES_NEXT_RE))(
        handle_friend_challenge_series_next
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_SHARE_RESULT_RE))(
        handle_friend_challenge_share_result
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.FRIEND_NEXT_RE))(
        handle_friend_challenge_next
    )


async def handle_friend_challenge_create(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.friend.challenge.create.choose"],
        reply_markup=build_friend_challenge_create_keyboard(),
    )
    await callback.answer()


async def handle_friend_challenge_create_selected(callback: CallbackQuery) -> None:
    gameplay = _gameplay()
    await friend_challenge_flow.handle_friend_challenge_create_selected(
        callback,
        session_local=gameplay.SessionLocal,
        user_onboarding_service=gameplay.UserOnboardingService,
        game_session_service=gameplay.GameSessionService,
        parse_challenge_rounds=gameplay_callbacks.parse_challenge_rounds,
        build_friend_invite_link=gameplay._build_friend_invite_link,
        build_friend_plan_text=gameplay._build_friend_plan_text,
        build_friend_ttl_text=gameplay._build_friend_ttl_text,
    )


async def handle_friend_challenge_rematch(callback: CallbackQuery) -> None:
    gameplay = _gameplay()
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
    gameplay = _gameplay()
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
    gameplay = _gameplay()
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
    gameplay = _gameplay()
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
    gameplay = _gameplay()
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
