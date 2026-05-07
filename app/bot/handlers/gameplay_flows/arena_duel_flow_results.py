from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.keyboards.duels import build_arena_published_keyboard, build_arena_result_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.analytics import ARENA_EVENT_ARENA_RESULT_SHOWN, build_arena_event_payload
from app.game.arena_duels.constants import ARENA_ATTEMPT_RESULT_DRAW, ARENA_ATTEMPT_RESULT_WIN
from app.game.arena_duels.types import ArenaAttemptCompletionResult, ArenaAttemptResultLine

from .arena_duel_flow_support import format_score_line, resolve_arena_user_label


async def send_arena_completion_result(
    callback: CallbackQuery,
    *,
    completion: ArenaAttemptCompletionResult,
    session_local,
    user_onboarding_service,
    emit_arena_analytics_event,
) -> None:
    if callback.message is None:
        return
    completed_attempt = getattr(completion, "completed_attempt", None)
    if completed_attempt is None:
        return

    opponent_attempt = getattr(completion, "opponent_attempt", None)
    if opponent_attempt is None:
        await callback.message.answer(
            TEXTS_DE["msg.duels.arena.published"].format(
                score_line=format_score_line(
                    score=completed_attempt.score,
                    time_ms=completed_attempt.time_ms,
                )
            ),
            reply_markup=build_arena_published_keyboard(duel_id=str(completion.duel.duel_id)),
        )
        await _emit_arena_result_shown(
            session_local=session_local,
            completion=completion,
            completed_attempt=completed_attempt,
            action="creator_baseline",
            emit_arena_analytics_event=emit_arena_analytics_event,
        )
        return

    async with session_local.begin() as session:
        opponent_label = await resolve_arena_user_label(
            session=session,
            user_onboarding_service=user_onboarding_service,
            user_id=opponent_attempt.user_id,
        )
    await callback.message.answer(
        _build_arena_result_text(
            completed_attempt=completed_attempt,
            opponent_attempt=opponent_attempt,
            opponent_label=opponent_label,
        ),
        reply_markup=build_arena_result_keyboard(
            user_won=completed_attempt.result == ARENA_ATTEMPT_RESULT_WIN,
            revanche_attempt_id=(
                None if opponent_attempt.attempt_id is None else str(opponent_attempt.attempt_id)
            ),
            close_loss=_is_close_loss(
                completed_attempt=completed_attempt,
                opponent_attempt=opponent_attempt,
            ),
        ),
    )
    await _emit_arena_result_shown(
        session_local=session_local,
        completion=completion,
        completed_attempt=completed_attempt,
        action="challenger",
        emit_arena_analytics_event=emit_arena_analytics_event,
    )


def _build_arena_result_text(
    *,
    completed_attempt: ArenaAttemptResultLine,
    opponent_attempt: ArenaAttemptResultLine,
    opponent_label: str,
) -> str:
    user_score_line = format_score_line(
        score=completed_attempt.score,
        time_ms=completed_attempt.time_ms,
    )
    opponent_score_line = format_score_line(
        score=opponent_attempt.score,
        time_ms=opponent_attempt.time_ms,
    )
    if completed_attempt.result == ARENA_ATTEMPT_RESULT_WIN:
        if completed_attempt.score == opponent_attempt.score:
            return TEXTS_DE["msg.duels.arena.result.win.time"].format(
                score=completed_attempt.score,
                user_score_line=user_score_line,
                opponent_label=opponent_label,
                opponent_score_line=opponent_score_line,
            )
        return TEXTS_DE["msg.duels.arena.result.win.score"].format(
            user_score_line=user_score_line,
            opponent_label=opponent_label,
            opponent_score_line=opponent_score_line,
        )
    if completed_attempt.result == ARENA_ATTEMPT_RESULT_DRAW:
        return TEXTS_DE["msg.duels.arena.result.draw"].format(
            score=completed_attempt.score,
            user_score_line=user_score_line,
            opponent_label=opponent_label,
            opponent_score_line=opponent_score_line,
        )
    if completed_attempt.score == opponent_attempt.score:
        return TEXTS_DE["msg.duels.arena.result.loss.time"].format(
            score=completed_attempt.score,
            user_score_line=user_score_line,
            opponent_label=opponent_label,
            opponent_score_line=opponent_score_line,
        )
    return TEXTS_DE["msg.duels.arena.result.loss.score"].format(
        user_score_line=user_score_line,
        opponent_label=opponent_label,
        opponent_score_line=opponent_score_line,
    )


def _is_close_loss(
    *,
    completed_attempt: ArenaAttemptResultLine,
    opponent_attempt: ArenaAttemptResultLine,
) -> bool:
    return (
        completed_attempt.result != ARENA_ATTEMPT_RESULT_WIN
        and completed_attempt.result != ARENA_ATTEMPT_RESULT_DRAW
        and completed_attempt.score == opponent_attempt.score
    )


async def _emit_arena_result_shown(
    *,
    session_local,
    completion: ArenaAttemptCompletionResult,
    completed_attempt: ArenaAttemptResultLine,
    action: str,
    emit_arena_analytics_event,
) -> None:
    async with session_local.begin() as session:
        await emit_arena_analytics_event(
            session,
            event_type=ARENA_EVENT_ARENA_RESULT_SHOWN,
            happened_at=datetime.now(timezone.utc),
            user_id=completed_attempt.user_id,
            payload=build_arena_event_payload(
                user_id=completed_attempt.user_id,
                arena_duel_id=completion.duel.duel_id,
                action=action,
                result=completed_attempt.result,
                score=completed_attempt.score,
                time_ms=completed_attempt.time_ms,
            ),
        )
