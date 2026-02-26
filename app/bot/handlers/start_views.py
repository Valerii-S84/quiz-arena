from __future__ import annotations

import html
from datetime import datetime

from app.bot.texts.de import TEXTS_DE
from app.game.modes.presentation import display_mode_label
from app.game.modes.rules import is_zero_cost_source
from app.game.sessions.service import FRIEND_CHALLENGE_LEVEL_SEQUENCE
from app.game.sessions.types import FriendChallengeSnapshot, StartSessionResult


def _build_friend_plan_text(*, total_rounds: int) -> str:
    rounds = max(1, int(total_rounds))
    sequence = list(FRIEND_CHALLENGE_LEVEL_SEQUENCE[:rounds])
    if rounds > len(FRIEND_CHALLENGE_LEVEL_SEQUENCE):
        sequence.extend(
            [FRIEND_CHALLENGE_LEVEL_SEQUENCE[-1]] * (rounds - len(FRIEND_CHALLENGE_LEVEL_SEQUENCE))
        )

    counts: dict[str, int] = {}
    for level in sequence:
        counts[level] = counts.get(level, 0) + 1
    mix_parts = [
        f"{level} x{counts[level]}"
        for level in ("A1", "A2", "B1", "B2", "C1", "C2")
        if level in counts
    ]
    mix = ", ".join(mix_parts) if mix_parts else "A1 x1"
    mode_label = "Sprint" if rounds <= 5 else "Mix"
    return f"{rounds} Fragen {mode_label}: {mix}. Keine Energie-Kosten."


def _build_friend_ttl_text(*, challenge: FriendChallengeSnapshot, now_utc: datetime) -> str | None:
    if challenge.status != "ACTIVE":
        return None
    if challenge.expires_at is None:
        return None
    remaining = challenge.expires_at - now_utc
    total_seconds = int(remaining.total_seconds())
    if total_seconds <= 0:
        return TEXTS_DE["msg.friend.challenge.expired"]
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return TEXTS_DE["msg.friend.challenge.ttl"].format(hours=hours, minutes=minutes)


def _build_home_text(*, free_energy: int, paid_energy: int, current_streak: int) -> str:
    if current_streak > 0:
        stats_line = TEXTS_DE["msg.home.stats.with_streak"].format(
            streak=current_streak,
            free_energy=free_energy,
            paid_energy=paid_energy,
        )
    else:
        stats_line = TEXTS_DE["msg.home.stats.no_streak"].format(
            free_energy=free_energy,
            paid_energy=paid_energy,
        )
    return "\n".join(
        [
            TEXTS_DE["msg.home.title"],
            stats_line,
            TEXTS_DE["msg.home.hint"],
        ]
    )


def _build_question_text(
    *,
    source: str,
    snapshot_free_energy: int,
    snapshot_paid_energy: int,
    start_result: StartSessionResult,
) -> str:
    theme_label = start_result.session.category or "Allgemein"
    question_number = start_result.session.question_number or 1
    total_questions = start_result.session.total_questions or 1
    mode_line = TEXTS_DE["msg.game.mode"].format(
        mode_code=display_mode_label(start_result.session.mode_code)
    )
    energy_line = TEXTS_DE["msg.game.energy.left"].format(
        free_energy=(
            snapshot_free_energy if is_zero_cost_source(source) else start_result.energy_free
        ),
        paid_energy=(
            snapshot_paid_energy if is_zero_cost_source(source) else start_result.energy_paid
        ),
    )
    theme_line = TEXTS_DE["msg.game.theme"].format(theme=theme_label)
    counter_line = TEXTS_DE["msg.game.question.counter"].format(
        current=question_number,
        total=total_questions,
    )
    return "\n".join(
        [
            f"<b>{html.escape(mode_line)}</b>",
            html.escape(energy_line),
            "",
            html.escape(theme_line),
            "",
            html.escape(counter_line),
            f"<b>{html.escape(start_result.session.text)}</b>",
            "",
            html.escape(TEXTS_DE["msg.game.choose_option"]),
        ]
    )


def _build_friend_score_text(
    *,
    challenge: FriendChallengeSnapshot,
    user_id: int,
    opponent_label: str,
) -> str:
    if challenge.creator_user_id == user_id:
        my_score = challenge.creator_score
        opponent_score = challenge.opponent_score
    else:
        my_score = challenge.opponent_score
        opponent_score = challenge.creator_score
    round_now = challenge.current_round
    if challenge.status == "COMPLETED":
        round_now = challenge.total_rounds
    return TEXTS_DE["msg.friend.challenge.score"].format(
        my_score=my_score,
        opponent_score=opponent_score,
        opponent_label=opponent_label,
        round_now=round_now,
        total_rounds=challenge.total_rounds,
    )
