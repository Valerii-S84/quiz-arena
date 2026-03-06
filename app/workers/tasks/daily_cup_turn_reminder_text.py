from __future__ import annotations

from app.bot.texts.de import TEXTS_DE
from app.game.tournaments.constants import TOURNAMENT_SELF_BOT_LABEL


def build_turn_reminder_text(*, opponent_label: str, deadline_text: str) -> str:
    return TEXTS_DE["msg.daily_cup.turn_reminder"].format(
        opponent_label=opponent_label,
        deadline=deadline_text,
    )


def resolve_turn_reminder_opponent_label(
    *,
    target_user_id: int,
    opponent_user_id: int,
    user_labels: dict[int, str],
) -> str:
    if target_user_id == opponent_user_id:
        return TOURNAMENT_SELF_BOT_LABEL
    return user_labels.get(opponent_user_id, "Spieler")
