from __future__ import annotations

from typing import Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.duels_access import build_duel_monetization_rows
from app.game.arena_duels.types import ArenaBeatenNotification
from app.game.duels.constants import ARENA_LIST_CALLBACK

BEATEN_NOTIFICATION_MIN_STRONG_SCORE = 4
BEATEN_NOTIFICATION_CLOSE_SCORE_DIFF = 1

BeatenNotificationActionMode = Literal["premium", "revanche_only", "arena_only"]
BeatenNotificationMoment = Literal["close_score", "close_time", "regular", "weak"]


def build_arena_beaten_notification_keyboard(
    *,
    source_attempt_id: str,
    action_mode: BeatenNotificationActionMode = "premium",
) -> InlineKeyboardMarkup:
    rows = []
    if action_mode != "arena_only":
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔁 Revanche",
                    callback_data=f"arena:revanche:{source_attempt_id}",
                )
            ]
        )
    if action_mode == "premium":
        rows.extend(build_duel_monetization_rows(paywall_context="beaten_result"))
    rows.append([InlineKeyboardButton(text="🏟 Zur Arena", callback_data=ARENA_LIST_CALLBACK)])
    return InlineKeyboardMarkup(
        inline_keyboard=rows,
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
    moment = classify_beaten_notification_moment(notification)
    if moment == "close_time":
        seconds_diff = format_seconds_diff(
            notification.previous_best_time_ms - notification.new_best_time_ms,
        )
        return (
            "⚔️ Du wurdest geschlagen – nur wegen der Zeit!\n\n"
            f"Du:\n{previous_score}\n\n"
            f"{challenger_label}:\n{new_score}\n\n"
            f"{seconds_diff} schneller.\n"
            "Revanche?"
        )
    if moment == "close_score":
        return (
            "⚔️ Dein Arena-Platz ist weg!\n\n"
            f"{challenger_label} hat dich überholt.\n\n"
            f"Du:\n{previous_score}\n\n"
            f"{challenger_label}:\n{new_score}\n\n"
            "+1 Antwort Unterschied.\n"
            "Hol dir deinen Platz zurück?"
        )
    if moment == "weak":
        return (
            "⚔️ Dein Arena-Duell wurde geschlagen.\n\n"
            f"{challenger_label} hat ein stärkeres Ergebnis gesetzt.\n\n"
            f"Du:\n{previous_score}\n\n"
            f"{challenger_label}:\n{new_score}\n\n"
            "Wähle ein neues Duell in der Arena."
        )

    score_diff = notification.new_best_score - notification.previous_best_score
    return (
        "⚔️ Dein Arena-Platz ist weg!\n\n"
        f"{challenger_label} hat dich überholt.\n\n"
        f"Du:\n{previous_score}\n\n"
        f"{challenger_label}:\n{new_score}\n\n"
        f"{score_diff} richtige Antworten Unterschied.\n"
        "Starte eine Revanche oder wähle ein neues Arena-Duell."
    )


def classify_beaten_notification_action_mode(
    notification: ArenaBeatenNotification,
) -> BeatenNotificationActionMode:
    moment = classify_beaten_notification_moment(notification)
    if moment in {"close_score", "close_time"}:
        return "premium"
    if moment == "weak":
        return "arena_only"
    return "revanche_only"


def classify_beaten_notification_moment(
    notification: ArenaBeatenNotification,
) -> BeatenNotificationMoment:
    if notification.previous_best_score < BEATEN_NOTIFICATION_MIN_STRONG_SCORE:
        return "weak"
    score_diff = notification.new_best_score - notification.previous_best_score
    if score_diff == BEATEN_NOTIFICATION_CLOSE_SCORE_DIFF:
        return "close_score"
    if score_diff == 0 and notification.new_best_time_ms < notification.previous_best_time_ms:
        return "close_time"
    return "regular"


def format_score_time(score: int, time_ms: int) -> str:
    seconds = max(0, int(round(time_ms / 1000)))
    return f"{score}/7 · {seconds // 60:02d}:{seconds % 60:02d}"


def format_seconds_diff(time_diff_ms: int) -> str:
    seconds = max(0, int(round(time_diff_ms / 1000)))
    unit = "Sekunde" if seconds == 1 else "Sekunden"
    return f"{seconds} {unit}"


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
