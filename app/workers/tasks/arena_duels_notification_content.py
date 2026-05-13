from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.duels_access import build_duel_monetization_rows
from app.game.arena_duels.types import ArenaBeatenNotification
from app.game.duels.constants import ARENA_LIST_CALLBACK


def build_arena_beaten_notification_keyboard(
    *,
    source_attempt_id: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔁 Revanche",
                    callback_data=f"arena:revanche:{source_attempt_id}",
                )
            ],
            *build_duel_monetization_rows(),
            [InlineKeyboardButton(text="🏟 Zur Arena", callback_data=ARENA_LIST_CALLBACK)],
        ]
    )


def build_notification_text(
    *,
    notification: ArenaBeatenNotification,
    challenger_label: str,
) -> str:
    previous_score = format_score_time(
        notification.previous_best_score,
        notification.previous_best_time_ms,
    )
    new_score = format_score_time(
        notification.new_best_score,
        notification.new_best_time_ms,
    )
    return (
        "⚔️ Dein Arena-Duell wurde geschlagen.\n\n"
        f"{challenger_label} hat dein Ergebnis übertroffen.\n\n"
        f"Du:\n{previous_score}\n\n"
        f"{challenger_label}:\n{new_score}"
    )


def format_score_time(score: int, time_ms: int) -> str:
    seconds = max(0, int(round(time_ms / 1000)))
    return f"{score}/7 · {seconds // 60:02d}:{seconds % 60:02d}"


def format_user_label(
    *,
    username: str | None,
    first_name: str | None,
    fallback: str,
) -> str:
    if username is not None and username.strip():
        return f"@{username.strip().lstrip('@')}"
    if first_name is not None and first_name.strip():
        return first_name.strip()
    return fallback
