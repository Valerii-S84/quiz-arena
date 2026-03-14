from __future__ import annotations

ZERO_COST_SOURCES = {
    "DAILY_CHALLENGE",
    "FRIEND_CHALLENGE",
    "TOURNAMENT",
}


def is_zero_cost_source(source: str) -> bool:
    return source in ZERO_COST_SOURCES
