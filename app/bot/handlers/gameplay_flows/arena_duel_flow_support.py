from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_views import _format_user_label
from app.bot.keyboards.duels import (
    build_arena_expired_guard_keyboard,
    build_arena_guard_back_keyboard,
    build_duel_paywall_keyboard,
)
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.constants import ARENA_ATTEMPT_RESULT_DRAW, ARENA_ATTEMPT_RESULT_WIN
from app.game.arena_duels.types import (
    ArenaAttemptResultLine,
    ArenaBaselineStartResult,
    ArenaChallengerStartResult,
)
from app.game.sessions.types import StartSessionResult

CLOSE_LOSS_MAX_TIME_DIFF_MS = 15_000
CLOSE_LOSS_MIN_SCORE = 4
CLOSE_LOSS_SCORE_DIFF = 1

DuelPaywallContext = Literal[
    "close_loss",
    "revanche_limit",
    "arena_accept_limit",
    "friend_limit",
    "beaten_result",
]

DUEL_PAYWALL_TEXT_KEYS: dict[DuelPaywallContext, str] = {
    "close_loss": "msg.duels.paywall.close_loss",
    "revanche_limit": "msg.duels.paywall.revanche_limit",
    "arena_accept_limit": "msg.duels.paywall.arena_accept_limit",
    "friend_limit": "msg.duels.paywall.friend_limit",
    "beaten_result": "msg.duels.paywall.beaten_result",
}


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


def is_close_loss(
    *,
    completed_attempt: ArenaAttemptResultLine,
    opponent_attempt: ArenaAttemptResultLine,
) -> bool:
    if completed_attempt.result == ARENA_ATTEMPT_RESULT_WIN:
        return False
    if completed_attempt.result == ARENA_ATTEMPT_RESULT_DRAW:
        return False

    score_diff = opponent_attempt.score - completed_attempt.score
    if completed_attempt.score == opponent_attempt.score:
        time_diff_ms = completed_attempt.time_ms - opponent_attempt.time_ms
        return 0 < time_diff_ms <= CLOSE_LOSS_MAX_TIME_DIFF_MS

    return score_diff == CLOSE_LOSS_SCORE_DIFF and completed_attempt.score >= CLOSE_LOSS_MIN_SCORE


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


def resolve_duel_paywall_text(*, context: DuelPaywallContext) -> str:
    return TEXTS_DE[DUEL_PAYWALL_TEXT_KEYS[context]]


async def send_duel_paywall(callback: CallbackQuery, *, context: DuelPaywallContext) -> None:
    if callback.message is not None:
        await callback.message.answer(
            resolve_duel_paywall_text(context=context),
            reply_markup=build_duel_paywall_keyboard(),
        )
    await callback.answer()
