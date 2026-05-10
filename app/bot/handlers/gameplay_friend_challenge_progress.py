from __future__ import annotations

from aiogram.types import CallbackQuery

from app.bot.handlers import gameplay_callbacks, gameplay_helpers, gameplay_views
from app.bot.handlers.gameplay_flows import (
    friend_challenge_flow,
    friend_challenge_result_share,
    friend_next_flow,
    friend_series_flow,
    proof_card_flow,
)
from app.bot.handlers.gameplay_friend_challenge_context import get_gameplay_module
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.duels import rollout as duel_rollout


async def _answer_duels_disabled(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.duels.disabled"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.duels.disabled"],
        reply_markup=build_home_keyboard(),
    )
    await callback.answer()


async def handle_friend_challenge_rematch(callback: CallbackQuery) -> None:
    if not duel_rollout.is_canonical_duels_enabled():
        await _answer_duels_disabled(callback)
        return
    gameplay = get_gameplay_module()
    await friend_challenge_flow.handle_friend_challenge_rematch(
        callback,
        friend_rematch_re=gameplay_callbacks.FRIEND_REMATCH_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=gameplay.SessionLocal,
        user_onboarding_service=gameplay.UserOnboardingService,
        game_session_service=gameplay.GameSessionService,
        resolve_opponent_label=gameplay._resolve_opponent_label,
        friend_opponent_user_id=gameplay_helpers._friend_opponent_user_id,
        notify_opponent=gameplay._notify_opponent,
        build_friend_plan_text=gameplay_views._build_friend_plan_text,
        build_friend_ttl_text=gameplay_views._build_friend_ttl_text,
    )


async def handle_friend_challenge_series_best3(callback: CallbackQuery) -> None:
    if not duel_rollout.is_canonical_duels_enabled():
        await _answer_duels_disabled(callback)
        return
    gameplay = get_gameplay_module()
    await friend_series_flow.handle_friend_challenge_series_best3(
        callback,
        friend_series_best3_re=gameplay_callbacks.FRIEND_SERIES_BEST3_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=gameplay.SessionLocal,
        user_onboarding_service=gameplay.UserOnboardingService,
        game_session_service=gameplay.GameSessionService,
        resolve_opponent_label=gameplay._resolve_opponent_label,
        friend_opponent_user_id=gameplay_helpers._friend_opponent_user_id,
        notify_opponent=gameplay._notify_opponent,
        build_friend_plan_text=gameplay_views._build_friend_plan_text,
        build_series_progress_text=gameplay_views._build_series_progress_text,
    )


async def handle_friend_challenge_series_next(callback: CallbackQuery) -> None:
    if not duel_rollout.is_canonical_duels_enabled():
        await _answer_duels_disabled(callback)
        return
    gameplay = get_gameplay_module()
    await friend_series_flow.handle_friend_challenge_series_next(
        callback,
        friend_series_next_re=gameplay_callbacks.FRIEND_SERIES_NEXT_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=gameplay.SessionLocal,
        user_onboarding_service=gameplay.UserOnboardingService,
        game_session_service=gameplay.GameSessionService,
        resolve_opponent_label=gameplay._resolve_opponent_label,
        friend_opponent_user_id=gameplay_helpers._friend_opponent_user_id,
        notify_opponent=gameplay._notify_opponent,
        build_friend_plan_text=gameplay_views._build_friend_plan_text,
        build_series_progress_text=gameplay_views._build_series_progress_text,
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
        build_friend_proof_card_text=gameplay_views._build_friend_proof_card_text,
        build_friend_result_share_url=_build_friend_result_share_url,
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
        build_friend_score_text=gameplay_views._build_friend_score_text,
        build_friend_ttl_text=gameplay_views._build_friend_ttl_text,
        send_friend_round_question=gameplay._send_friend_round_question,
    )


async def _build_friend_result_share_url(
    callback: CallbackQuery,
    *,
    proof_card_text: str,
) -> str | None:
    return await friend_challenge_result_share.build_result_share_url(
        callback=callback,
        proof_card_text=proof_card_text,
    )
