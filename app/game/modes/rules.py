from __future__ import annotations

from app.game.modes.catalog import FREE_MODE_CODES

ZERO_COST_SOURCES = {
    "DAILY_CHALLENGE",
    "FRIEND_CHALLENGE",
    "TOURNAMENT",
}


def is_mode_allowed(*, mode_code: str, premium_active: bool, has_mode_access: bool) -> bool:
    if premium_active:
        return True
    if mode_code in FREE_MODE_CODES:
        return True
    return has_mode_access


def is_zero_cost_source(source: str) -> bool:
    return source in ZERO_COST_SOURCES
