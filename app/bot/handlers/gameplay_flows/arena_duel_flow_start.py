from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.analytics import (
    ARENA_EVENT_DUEL_LIMIT_HIT,
    ARENA_EVENT_DUEL_PAYWALL_SHOWN,
    build_arena_event_payload,
    emit_arena_analytics_event,
)
from app.game.arena_duels.errors import (
    ArenaDuelAccessError,
    ArenaDuelAlreadyAttemptedError,
    ArenaDuelExpiredError,
    ArenaDuelNotFoundError,
    ArenaDuelOwnAttemptError,
    ArenaDuelPaymentRequiredError,
)
from app.game.questions.catalog import QUICK_MIX_MODE_CODE
from app.game.sessions.errors import FriendChallengeAccessError

from .arena_duel_flow_support import (
    build_arena_guard_keyboard,
    extract_start_result,
    send_arena_guard,
    send_duel_paywall,
)


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
    guard_text_key: str | None = None
    payment_required = False
    result: object | None = None
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            access_type = await resolve_access_type(
                session, user_id=snapshot.user_id, now_utc=now_utc
            )
            result = await start_arena_round(session, snapshot.user_id, now_utc, access_type)
        except ArenaDuelPaymentRequiredError:
            payment_required = True
            action = _arena_action_from_callback_data(callback.data)
            await emit_arena_analytics_event(
                session,
                event_type=ARENA_EVENT_DUEL_LIMIT_HIT,
                happened_at=now_utc,
                user_id=snapshot.user_id,
                payload=build_arena_event_payload(user_id=snapshot.user_id, action=action),
            )
            await emit_arena_analytics_event(
                session,
                event_type=ARENA_EVENT_DUEL_PAYWALL_SHOWN,
                happened_at=now_utc,
                user_id=snapshot.user_id,
                payload=build_arena_event_payload(user_id=snapshot.user_id, action=action),
            )
        except ArenaDuelOwnAttemptError:
            guard_text_key = "msg.duels.arena.own"
        except ArenaDuelAlreadyAttemptedError:
            guard_text_key = "msg.duels.arena.already_played"
        except (
            ArenaDuelExpiredError,
            ArenaDuelNotFoundError,
            ArenaDuelAccessError,
            FriendChallengeAccessError,
        ):
            guard_text_key = "msg.duels.arena.expired"

    if payment_required:
        await send_duel_paywall(callback, context="arena_accept_limit")
        return
    if guard_text_key is not None:
        await send_arena_guard(
            callback,
            text_key=guard_text_key,
            reply_markup=build_arena_guard_keyboard(guard_text_key),
        )
        return

    start_result = extract_start_result(result)
    if start_result is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    await callback.message.answer(
        build_question_text(
            source="ARENA_DUEL",
            snapshot_free_energy=snapshot.free_energy,
            snapshot_paid_energy=snapshot.paid_energy,
            start_result=start_result,
        ),
        reply_markup=build_quiz_keyboard(
            session_id=str(start_result.session.session_id),
            options=start_result.session.options,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


def _arena_action_from_callback_data(callback_data: str | None) -> str:
    if callback_data == "arena:start_create":
        return "create"
    if callback_data is not None and callback_data.startswith("arena:start_attempt:"):
        return "accept"
    return "arena"
