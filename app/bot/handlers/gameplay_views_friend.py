from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from app.bot.handlers.gameplay_views_friend_proof import _build_friend_proof_card_text
from app.bot.handlers.gameplay_views_friend_results import (
    _build_friend_finish_text,
    _build_friend_signature,
    _build_public_badge_label,
)
from app.bot.texts.de import TEXTS_DE
from app.game.friend_challenges.constants import is_duel_active_status

if TYPE_CHECKING:
    from app.game.sessions.types import FriendChallengeSnapshot


__all__ = [
    "_build_friend_finish_text",
    "_build_friend_plan_text",
    "_build_friend_proof_card_text",
    "_build_friend_score_text",
    "_build_friend_signature",
    "_build_friend_ttl_text",
    "_build_public_badge_label",
    "_build_series_progress_text",
    "_format_user_label",
]


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
    return f"{rounds} Fragen. Keine Energie-Kosten."


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


def _build_friend_ttl_text(*, challenge: FriendChallengeSnapshot, now_utc: datetime) -> str | None:
    if not is_duel_active_status(challenge.status):
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
