from __future__ import annotations

from app.bot.handlers.start_views import _build_home_text
from app.bot.texts.de import TEXTS_DE


def test_build_home_text_without_badge_line() -> None:
    text = _build_home_text(
        free_energy=20,
        paid_energy=3,
        current_streak=2,
        best_streak=5,
        daily_cup_badge_unlocked=False,
    )
    assert "Serie: 2 | Beste: 5" in text
    assert TEXTS_DE["msg.home.badge.daily_cup_5"] not in text


def test_build_home_text_with_badge_line() -> None:
    text = _build_home_text(
        free_energy=20,
        paid_energy=3,
        current_streak=2,
        best_streak=5,
        daily_cup_badge_unlocked=True,
    )
    assert TEXTS_DE["msg.home.badge.daily_cup_5"] in text


def test_build_home_text_shows_best_streak_even_when_current_is_zero() -> None:
    text = _build_home_text(
        free_energy=20,
        paid_energy=3,
        current_streak=0,
        best_streak=7,
        daily_cup_badge_unlocked=False,
    )
    assert "Serie: 0 | Beste: 7" in text
