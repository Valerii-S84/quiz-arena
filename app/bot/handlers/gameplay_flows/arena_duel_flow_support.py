from __future__ import annotations

from uuid import UUID

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_views import _format_user_label
from app.bot.keyboards.duels import (
    build_arena_expired_guard_keyboard,
    build_arena_guard_back_keyboard,
)
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.constants import ARENA_ATTEMPT_RESULT_DRAW, ARENA_ATTEMPT_RESULT_WIN
from app.game.arena_duels.types import (
    ArenaAttemptResultLine,
    ArenaBaselineStartResult,
    ArenaChallengerStartResult,
)
from app.game.sessions.types import StartSessionResult


def extract_start_result(result: object | None) -> StartSessionResult | None:
    if result is None:
        return None
    if isinstance(result, ArenaBaselineStartResult):
        return result.start_result
    if isinstance(result, ArenaChallengerStartResult):
        return result.start_result
    return getattr(result, "start_result", None)


def parse_arena_duel_id(callback: CallbackQuery, *, pattern, parse_uuid_callback) -> UUID | None:
    if callback.data is None:
        return None
    return parse_uuid_callback(pattern=pattern, callback_data=callback.data)


def format_score_line(*, score: int, time_ms: int) -> str:
    total_seconds = max(0, int(round(time_ms / 1000)))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{score}/7 · {minutes:02d}:{seconds:02d}"


def build_arena_result_text(
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


async def resolve_arena_user_label(*, session, user_onboarding_service, user_id: int) -> str:
    user = await user_onboarding_service.get_by_id(session, user_id)
    if user is None:
        return f"Spieler #{user_id}"
    return _format_user_label(
        username=user.username,
        first_name=user.first_name,
        fallback=f"Spieler #{user_id}",
    )


def build_arena_guard_keyboard(text_key: str) -> object:
    if text_key == "msg.duels.arena.expired":
        return build_arena_expired_guard_keyboard()
    return build_arena_guard_back_keyboard()


async def send_arena_guard(callback: CallbackQuery, *, text_key: str, reply_markup) -> None:
    if callback.message is not None:
        await callback.message.answer(TEXTS_DE[text_key], reply_markup=reply_markup)
    await callback.answer()
