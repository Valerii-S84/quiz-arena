from __future__ import annotations

from app.bot.texts.de import TEXTS_DE
from app.game.duels import rollout as duel_rollout


def build_unplayed_friend_challenge_text(*, can_publish_to_arena: bool) -> str:
    can_publish_to_arena = can_publish_to_arena and duel_rollout.is_canonical_duels_enabled()
    hint_key = (
        "msg.friend.challenge.reminder.publish_hint"
        if can_publish_to_arena
        else "msg.friend.challenge.reminder.wait_or_close_hint"
    )
    return "\n\n".join(
        [
            TEXTS_DE["msg.friend.challenge.reminder.unplayed"],
            TEXTS_DE[hint_key],
        ]
    )


def build_expired_duel_texts(
    *,
    status: str,
    creator_score: int,
    opponent_score: int,
) -> tuple[str, str]:
    if status == "WALKOVER":
        return (
            "⌛ Duell kampflos beendet.\n"
            f"Endstand: Du {creator_score} | Freund {opponent_score}.",
            "⌛ Duell kampflos beendet.\n"
            f"Endstand: Du {opponent_score} | Freund {creator_score}.",
        )
    return (
        "⌛ Dein Duell ist wegen Zeitablauf beendet.\n"
        f"Endstand: Du {creator_score} | Freund {opponent_score}.",
        "⌛ Dein Duell ist wegen Zeitablauf beendet.\n"
        f"Endstand: Du {opponent_score} | Freund {creator_score}.",
    )
