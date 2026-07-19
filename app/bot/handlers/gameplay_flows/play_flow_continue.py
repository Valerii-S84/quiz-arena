from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.play_flow_context import ContinueModeFlowServices
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.errors import ArenaDuelError
from app.game.arena_duels.types import ArenaBeatenNotification
from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.sessions.errors import EnergyInsufficientError, FriendChallengeAccessError
from app.game.sessions.types import AnswerSessionResult


@dataclass
class ContinueOutcome:
    snapshot: Any | None = None
    next_result: Any | None = None
    arena_completion: Any | None = None
    arena_notification: ArenaBeatenNotification | None = None
    arena_attempt_completed: bool = False
    handled: bool = False


async def continue_regular_mode_after_answer_impl(
    callback: CallbackQuery,
    *,
    result: AnswerSessionResult,
    user_id: int | None = None,
    now_utc: datetime,
    services: ContinueModeFlowServices,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    del user_id
    outcome = await _resolve_continue_outcome(callback, result, now_utc, services)
    if outcome.handled:
        return
    if outcome.arena_attempt_completed:
        from app.bot.handlers.gameplay_flows.play_flow_arena_completion import (
            handle_arena_completion,
        )

        await handle_arena_completion(callback, outcome, now_utc, services)
        return
    if outcome.snapshot is None or outcome.next_result is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await _send_next_question(callback, result, outcome.snapshot, outcome.next_result, services)
    await callback.answer()


async def _resolve_continue_outcome(
    callback: CallbackQuery,
    result: AnswerSessionResult,
    now_utc: datetime,
    services: ContinueModeFlowServices,
) -> ContinueOutcome:
    async with services.session_local.begin() as session:
        snapshot = await services.user_onboarding_service.ensure_home_snapshot(
            session, telegram_user=callback.from_user
        )
        return await _resolve_continue_with_session(
            callback, session, snapshot, result, now_utc, services
        )


async def _resolve_continue_with_session(
    callback: CallbackQuery,
    session,
    snapshot,
    result: AnswerSessionResult,
    now_utc: datetime,
    services: ContinueModeFlowServices,
) -> ContinueOutcome:
    try:
        start_kwargs = _build_start_kwargs(snapshot, result, callback.id, now_utc)
        if result.source == "ARENA_DUEL":
            arena_outcome = await _resolve_arena_outcome(
                callback, session, snapshot, result, now_utc, services, start_kwargs
            )
            if arena_outcome is not None:
                return arena_outcome
        next_result = await services.game_session_service.start_session(session, **start_kwargs)
        return ContinueOutcome(snapshot=snapshot, next_result=next_result)
    except (ArenaDuelError, FriendChallengeAccessError):
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return ContinueOutcome(handled=True)
    except EnergyInsufficientError:
        await services.energy_handler(
            callback,
            session=session,
            user_id=snapshot.user_id,
            now_utc=now_utc,
            offer_service=services.offer_service,
            offer_logging_error=services.offer_logging_error,
            offer_idempotency_key=f"offer:energy:auto:{callback.id}",
            channel_bonus_service=services.channel_bonus_service,
        )
        await callback.answer()
        return ContinueOutcome(handled=True)


def _build_start_kwargs(snapshot, result: AnswerSessionResult, callback_id: str, now_utc: datetime):
    return {
        "user_id": snapshot.user_id,
        "mode_code": result.mode_code,
        "source": result.source,
        "idempotency_key": f"start:auto:{result.mode_code}:{callback_id}",
        "now_utc": now_utc,
        "preferred_question_level": result.next_preferred_level,
    }


async def _resolve_arena_outcome(
    callback: CallbackQuery,
    session,
    snapshot,
    result: AnswerSessionResult,
    now_utc: datetime,
    services: ContinueModeFlowServices,
    start_kwargs,
) -> ContinueOutcome | None:
    if result.arena_attempt_id is None or result.arena_answered_round is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return ContinueOutcome(handled=True)

    next_arena_round = result.arena_answered_round + 1
    if next_arena_round <= DUEL_QUESTION_COUNT:
        start_kwargs.update(
            {
                "arena_attempt_id": result.arena_attempt_id,
                "arena_round": next_arena_round,
                "duel_limit_checked": True,
            }
        )
        return None

    completion = await services.game_session_service.complete_arena_attempt_if_applicable(
        session,
        attempt_id=result.arena_attempt_id,
        user_id=snapshot.user_id,
        now_utc=now_utc,
    )
    return ContinueOutcome(
        arena_completion=completion,
        arena_notification=completion.beaten_notification if completion is not None else None,
        arena_attempt_completed=True,
    )


async def _send_next_question(
    callback: CallbackQuery,
    result: AnswerSessionResult,
    snapshot,
    next_result,
    services: ContinueModeFlowServices,
) -> None:
    if callback.message is None:
        return

    question_text = services.build_question_text(
        source=result.source,
        snapshot_free_energy=snapshot.free_energy,
        snapshot_paid_energy=snapshot.paid_energy,
        start_result=next_result,
    )
    await callback.message.answer(
        question_text,
        reply_markup=build_quiz_keyboard(
            session_id=str(next_result.session.session_id),
            options=next_result.session.options,
        ),
        parse_mode="HTML",
    )
