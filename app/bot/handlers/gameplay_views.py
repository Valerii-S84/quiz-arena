from __future__ import annotations

import html
from datetime import datetime
from typing import TYPE_CHECKING

from app.bot.texts.de import TEXTS_DE
from app.game.friend_challenges.ui_contract import FRIEND_CHALLENGE_LEVEL_SEQUENCE
from app.game.modes.presentation import display_mode_label
from app.game.modes.rules import is_zero_cost_source

if TYPE_CHECKING:
    from app.game.sessions.types import FriendChallengeSnapshot, StartSessionResult


def _format_user_label(
    *, username: str | None, first_name: str | None, fallback: str = "Freund"
) -> str:
    if username:
        normalized = username.strip()
        if normalized:
            return f"@{normalized}"
    if first_name:
        normalized_name = first_name.strip()
        if normalized_name:
            return normalized_name
    return fallback


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


def _build_friend_finish_text(
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

    if challenge.status == "EXPIRED":
        outcome_text = TEXTS_DE["msg.friend.challenge.finished.expired"]
    elif challenge.winner_user_id is None:
        outcome_text = TEXTS_DE["msg.friend.challenge.finished.draw"]
    elif challenge.winner_user_id == user_id:
        outcome_text = TEXTS_DE["msg.friend.challenge.finished.win"]
    else:
        outcome_text = TEXTS_DE["msg.friend.challenge.finished.lose"].format(
            opponent_label=opponent_label
        )

    summary_text = TEXTS_DE["msg.friend.challenge.finished.summary"].format(
        my_score=my_score,
        opponent_score=opponent_score,
        opponent_label=opponent_label,
    )
    return "\n".join([outcome_text, summary_text])


def _build_friend_signature(*, challenge: FriendChallengeSnapshot, user_id: int) -> str:
    if challenge.creator_user_id == user_id:
        my_score = challenge.creator_score
        opponent_score = challenge.opponent_score
    else:
        my_score = challenge.opponent_score
        opponent_score = challenge.creator_score

    score_diff = my_score - opponent_score
    if challenge.status == "EXPIRED":
        return "Deadline Survivor"
    if score_diff >= 3:
        return "Artikel-Koenig"
    if score_diff > 0:
        return "Satzbau-Boss"
    if score_diff == 0:
        return "Rematch-Magnet"
    if score_diff <= -3:
        return "Chaos im Satzbau"
    return "Revanche-Laeufer"


def _build_public_badge_label(
    *,
    challenge: FriendChallengeSnapshot,
    user_id: int,
    series_my_wins: int = 0,
    series_opponent_wins: int = 0,
) -> str:
    if challenge.series_best_of > 1 and series_my_wins > series_opponent_wins:
        return "Series Closer"
    return _build_friend_signature(challenge=challenge, user_id=user_id)


def _build_series_progress_text(
    *,
    game_no: int,
    best_of: int,
    my_wins: int,
    opponent_wins: int,
    opponent_label: str,
) -> str:
    return TEXTS_DE["msg.friend.challenge.series.progress"].format(
        game_no=game_no,
        best_of=best_of,
        my_wins=my_wins,
        opponent_label=opponent_label,
        opponent_wins=opponent_wins,
    )


def _build_friend_proof_card_text(
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

    if challenge.status == "EXPIRED":
        winner_label = "Zeit abgelaufen"
    elif challenge.winner_user_id is None:
        winner_label = "Unentschieden"
    elif challenge.winner_user_id == user_id:
        winner_label = "Du"
    else:
        winner_label = opponent_label

    signature = _build_friend_signature(challenge=challenge, user_id=user_id)
    return "\n".join(
        [
            TEXTS_DE["msg.friend.challenge.proof.title"],
            TEXTS_DE["msg.friend.challenge.proof.winner"].format(winner_label=winner_label),
            TEXTS_DE["msg.friend.challenge.proof.score"].format(
                my_score=my_score,
                opponent_label=opponent_label,
                opponent_score=opponent_score,
            ),
            TEXTS_DE["msg.friend.challenge.proof.format"].format(
                total_rounds=challenge.total_rounds
            ),
            TEXTS_DE["msg.friend.challenge.proof.signature"].format(signature=signature),
        ]
    )


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
