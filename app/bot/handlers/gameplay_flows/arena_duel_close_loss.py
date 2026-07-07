from __future__ import annotations

from app.game.arena_duels.constants import ARENA_ATTEMPT_RESULT_DRAW, ARENA_ATTEMPT_RESULT_WIN
from app.game.arena_duels.types import ArenaAttemptResultLine

CLOSE_LOSS_MAX_TIME_DIFF_MS = 15_000
CLOSE_LOSS_MIN_SCORE = 4
CLOSE_LOSS_SCORE_DIFF = 1


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


def format_close_loss_difference(
    *,
    completed_attempt: ArenaAttemptResultLine,
    opponent_attempt: ArenaAttemptResultLine,
) -> str:
    if completed_attempt.score == opponent_attempt.score:
        seconds = max(0, int(round((completed_attempt.time_ms - opponent_attempt.time_ms) / 1000)))
        unit = "Sekunde" if seconds == 1 else "Sekunden"
        return f"Nur {seconds} {unit} Unterschied."
    score_diff = max(0, opponent_attempt.score - completed_attempt.score)
    unit = "Antwort" if score_diff == 1 else "Antworten"
    return f"Nur {score_diff} {unit} Unterschied."
