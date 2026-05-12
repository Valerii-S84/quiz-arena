from __future__ import annotations

from typing import TYPE_CHECKING

from app.bot.handlers.gameplay_views_friend_results import (
    _build_friend_signature,
    _format_friend_result_line,
    _resolve_friend_result_values,
)
from app.bot.texts.de import TEXTS_DE

if TYPE_CHECKING:
    from app.game.sessions.types import FriendChallengeSnapshot


def _build_friend_proof_card_text(
    *,
    challenge: FriendChallengeSnapshot,
    user_id: int,
    opponent_label: str,
) -> str:
    my_score, opponent_score, my_time_ms, opponent_time_ms = _resolve_friend_result_values(
        challenge=challenge,
        user_id=user_id,
    )

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
            ),
            TEXTS_DE["msg.friend.challenge.proof.format"].format(
                total_rounds=challenge.total_rounds
            ),
            TEXTS_DE["msg.friend.challenge.proof.signature"].format(signature=signature),
        ]
    )
