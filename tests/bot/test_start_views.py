from __future__ import annotations

from app.bot.handlers.start_views import _build_home_text
from app.bot.texts.de import TEXTS_DE


def test_build_home_text_hides_premium_when_inactive() -> None:
    text = _build_home_text(
        free_energy=18,
        paid_energy=3,
        current_streak=19,
        best_streak=19,
        global_best_streak=45,
        premium_active=False,
        daily_cup_badge_unlocked=False,
    )

    assert text == (
        "Serie: 19 | Beste: 19 | 🏆 Rekord: 45\n" "⚡ 18/20\n" f"{TEXTS_DE['msg.home.hint']}"
    )
    assert "💎" not in text


def test_build_home_text_shows_premium_when_active() -> None:
    text = _build_home_text(
        free_energy=18,
        paid_energy=3,
        current_streak=19,
        best_streak=19,
        global_best_streak=45,
        premium_active=True,
        daily_cup_badge_unlocked=False,
    )

    assert "⚡ 18/20 | 💎 Premium aktiv" in text


def test_build_home_text_shows_zero_streak_without_error() -> None:
    text = _build_home_text(
        free_energy=20,
        paid_energy=0,
        current_streak=0,
        best_streak=0,
        global_best_streak=27,
        premium_active=False,
        daily_cup_badge_unlocked=False,
    )

    assert "Serie: 0 | Beste: 0 | 🏆 Rekord: 27" in text


def test_build_home_text_keeps_badge_line_when_unlocked() -> None:
    text = _build_home_text(
        free_energy=18,
        paid_energy=0,
        current_streak=19,
        best_streak=19,
        global_best_streak=45,
        premium_active=False,
        daily_cup_badge_unlocked=True,
    )

    assert TEXTS_DE["msg.home.badge.daily_cup_5"] in text
