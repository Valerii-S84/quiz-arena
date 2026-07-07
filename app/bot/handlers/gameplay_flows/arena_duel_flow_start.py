from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.questions.catalog import QUICK_MIX_MODE_CODE

from .arena_duel_flow_start_runtime import resolve_arena_start_outcome
from .arena_duel_flow_support import (
    build_arena_guard_keyboard,
    extract_start_result,
    send_arena_guard,
)
from .arena_duel_paywall import send_duel_paywall


async def handle_arena_start_create(
    callback: CallbackQuery,
    *,
    session_local,
    user_onboarding_service,
    resolve_arena_create_access_type,
    create_arena_duel_baseline,
    build_question_text,
) -> None:
    await _start_arena_round(
        callback,
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        resolve_access_type=resolve_arena_create_access_type,
        start_arena_round=lambda session, user_id, now_utc, access_type: create_arena_duel_baseline(
            session,
            creator_user_id=user_id,
            mode_code=QUICK_MIX_MODE_CODE,
            now_utc=now_utc,
            access_type=access_type,
        ),
        build_question_text=build_question_text,
    )


async def handle_arena_start_attempt(
    callback: CallbackQuery,
    *,
    duel_id,
    session_local,
    user_onboarding_service,
    resolve_arena_accept_access_type,
    accept_arena_duel,
    build_question_text,
) -> None:
    await _start_arena_round(
        callback,
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        resolve_access_type=resolve_arena_accept_access_type,
        start_arena_round=lambda session, user_id, now_utc, access_type: accept_arena_duel(
            session,
            duel_id=duel_id,
            user_id=user_id,
            now_utc=now_utc,
            access_type=access_type,
        ),
        build_question_text=build_question_text,
    )


async def _start_arena_round(
    callback: CallbackQuery,
    *,
    session_local,
    user_onboarding_service,
    resolve_access_type,
    start_arena_round: Callable[[object, int, datetime, str], Awaitable[object]],
    build_question_text,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    outcome = await resolve_arena_start_outcome(
        callback,
        session_local=session_local,
        user_onboarding_service=user_onboarding_service,
        resolve_access_type=resolve_access_type,
        start_arena_round=start_arena_round,
        now_utc=now_utc,
    )

    if outcome.payment_required:
        await send_duel_paywall(callback, context="arena_limit")
        return
    if outcome.guard_text_key is not None:
        await send_arena_guard(
            callback,
            text_key=outcome.guard_text_key,
            reply_markup=build_arena_guard_keyboard(outcome.guard_text_key),
        )
        return

    start_result = extract_start_result(outcome.result)
    if start_result is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    await callback.message.answer(
        build_question_text(
            source="ARENA_DUEL",
            snapshot_free_energy=outcome.snapshot.free_energy,
            snapshot_paid_energy=outcome.snapshot.paid_energy,
            start_result=start_result,
        ),
        reply_markup=build_quiz_keyboard(
            session_id=str(start_result.session.session_id),
            options=start_result.session.options,
        ),
        parse_mode="HTML",
    )
    await callback.answer()
