from __future__ import annotations

from app.game.duels.constants import DUEL_LIMITED_SESSION_SOURCES

ZERO_COST_SOURCES = {
    "ARENA_DUEL",
    "DAILY_CHALLENGE",
    "FRIEND_CHALLENGE",
    "TOURNAMENT",
}


def is_zero_cost_source(source: str) -> bool:
    return source in ZERO_COST_SOURCES


def requires_duel_limit_gate(source: str) -> bool:
    return source in DUEL_LIMITED_SESSION_SOURCES
