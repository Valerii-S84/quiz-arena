from __future__ import annotations

from app.core.telegram_links import public_bot_link


def resolve_user_label(*, user, fallback: str) -> str:
    if user is None:
        return fallback
    if user.username:
        return f"@{str(user.username).strip()}"
    if user.first_name:
        return str(user.first_name).strip() or fallback
    return fallback


def build_caption(
    *,
    challenge_id: str,
    status: str,
    role: str,
    creator_score: int,
    opponent_score: int,
) -> str:
    if role == "creator":
        my_score = creator_score
        other_score = opponent_score
    else:
        my_score = opponent_score
        other_score = creator_score
    if status == "WALKOVER":
        prefix = "⌛ DUELL WALKOVER"
    elif status == "EXPIRED":
        prefix = "⌛ DUELL ABGELAUFEN"
    else:
        prefix = "🏆 DUELL ERGEBNIS"
    return (
        f"{prefix}\n"
        f"Score: Du {my_score} : Gegner {other_score}\n"
        f"ID: {challenge_id}\n"
        f"📱 {public_bot_link()}"
    )
