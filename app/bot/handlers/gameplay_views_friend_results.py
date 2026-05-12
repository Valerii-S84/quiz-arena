from __future__ import annotations

from typing import TYPE_CHECKING

from app.bot.texts.de import TEXTS_DE

if TYPE_CHECKING:
    from app.game.sessions.types import FriendChallengeSnapshot


def _format_duel_time(time_ms: int | None) -> str | None:
    if time_ms is None:
        return None
    seconds = max(0, int(round(time_ms / 1000)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _format_friend_result_line(
    *,
    score: int,
    total_rounds: int,
    time_ms: int | None,
) -> str:
    score_line = f"{score}/{total_rounds}"
    time_text = _format_duel_time(time_ms)
    if time_text is None:
        return score_line
    return f"{score_line} · {time_text}"


def _resolve_friend_result_values(
    *,
    challenge: FriendChallengeSnapshot,
    user_id: int,
) -> tuple[int, int, int | None, int | None]:
    if challenge.creator_user_id == user_id:
        return (
            challenge.creator_score,
            challenge.opponent_score,
            challenge.creator_time_ms,
            challenge.opponent_time_ms,
        )
    return (
        challenge.opponent_score,
        challenge.creator_score,
        challenge.opponent_time_ms,
        challenge.creator_time_ms,
    )


def _build_friend_outcome_text(
    *,
    challenge: FriendChallengeSnapshot,
    user_id: int,
    opponent_label: str,
    my_score: int,
    opponent_score: int,
    my_time_ms: int | None,
    opponent_time_ms: int | None,
) -> str:
    if challenge.status == "EXPIRED":
        return TEXTS_DE["msg.friend.challenge.finished.expired"]
    if challenge.winner_user_id is None:
        return TEXTS_DE["msg.friend.challenge.finished.draw"].format(
            score=my_score,
            total_rounds=challenge.total_rounds,
        )
    if challenge.winner_user_id == user_id:
        if my_score == opponent_score and my_time_ms is not None and opponent_time_ms is not None:
            return TEXTS_DE["msg.friend.challenge.finished.win.time"].format(
                score=my_score,
                total_rounds=challenge.total_rounds,
            )
        return TEXTS_DE["msg.friend.challenge.finished.win.score"].format(
            opponent_label=opponent_label,
        )
    if my_score == opponent_score and my_time_ms is not None and opponent_time_ms is not None:
        return TEXTS_DE["msg.friend.challenge.finished.lose.time"].format(
            score=my_score,
            total_rounds=challenge.total_rounds,
            opponent_label=opponent_label,
        )
    return TEXTS_DE["msg.friend.challenge.finished.lose.score"].format(
        opponent_label=opponent_label,
    )


def _build_friend_finish_text(
    *,
    challenge: FriendChallengeSnapshot,
    user_id: int,
    opponent_label: str,
) -> str:
    my_score, opponent_score, my_time_ms, opponent_time_ms = _resolve_friend_result_values(
        challenge=challenge,
        user_id=user_id,
    )

    outcome_text = _build_friend_outcome_text(
        challenge=challenge,
        user_id=user_id,
        opponent_label=opponent_label,
        my_score=my_score,
        opponent_score=opponent_score,
        my_time_ms=my_time_ms,
        opponent_time_ms=opponent_time_ms,
    )
    summary_text = TEXTS_DE["msg.friend.challenge.finished.summary"].format(
        my_score_line=_format_friend_result_line(
            score=my_score,
            total_rounds=challenge.total_rounds,
            time_ms=my_time_ms,
        ),
        opponent_label=opponent_label,
        opponent_score_line=_format_friend_result_line(
            score=opponent_score,
            total_rounds=challenge.total_rounds,
            time_ms=opponent_time_ms,
        ),
    )
    return "\n".join([outcome_text, summary_text])


def _build_friend_signature(*, challenge: FriendChallengeSnapshot, user_id: int) -> str:
    my_score, opponent_score, _, _ = _resolve_friend_result_values(
        challenge=challenge,
        user_id=user_id,
    )

    score_diff = my_score - opponent_score
    if challenge.status == "EXPIRED":
        return "Zeitfenster gehalten"
    if score_diff >= 3:
        return "Artikel-König"
    if score_diff > 0:
        return "Satzbau-Meister"
    if score_diff == 0:
        return "Revanche-Magnet"
    if score_diff <= -3:
        return "Chaos im Satzbau"
    return "Revanche-Läufer"


def _build_public_badge_label(
    *,
    challenge: FriendChallengeSnapshot,
    user_id: int,
    series_my_wins: int = 0,
    series_opponent_wins: int = 0,
) -> str:
    if challenge.series_best_of > 1 and series_my_wins > series_opponent_wins:
        return "Serien-Sieger"
    return _build_friend_signature(challenge=challenge, user_id=user_id)
