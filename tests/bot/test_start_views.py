from __future__ import annotations

from app.bot.handlers.start_views import _build_home_text
from app.bot.texts.de import TEXTS_DE


def test_build_home_text_without_badge_line() -> None:
    text = _build_home_text(
        free_energy=20,
        paid_energy=3,
        current_streak=2,
        daily_cup_badge_unlocked=False,
    )
    assert TEXTS_DE["msg.home.badge.daily_cup_5"] not in text


def test_build_home_text_with_badge_line() -> None:
    text = _build_home_text(
        free_energy=20,
        paid_energy=3,
        current_streak=2,
        daily_cup_badge_unlocked=True,
    )
    assert TEXTS_DE["msg.home.badge.daily_cup_5"] in text
