from __future__ import annotations

from app.core.config import get_settings

FRIEND_CHALLENGE_TOTAL_ROUNDS = 12
FRIEND_CHALLENGE_FREE_CREATES = 2
FRIEND_CHALLENGE_TICKET_PRODUCT_CODE = "FRIEND_CHALLENGE_5"
FRIEND_CHALLENGE_TTL_SECONDS = max(60, int(get_settings().friend_challenge_ttl_seconds))
DAILY_CHALLENGE_TOTAL_QUESTIONS = 7
FRIEND_CHALLENGE_LEVEL_SEQUENCE: tuple[str, ...] = (
    "A1",
    "A1",
    "A1",
    "A2",
    "A2",
    "A2",
    "A2",
    "A2",
    "A2",
    "B1",
    "B1",
    "B1",
)
LEVEL_ORDER: tuple[str, ...] = ("A1", "A2", "B1", "B2", "C1", "C2")
PERSISTENT_ADAPTIVE_MODE_BOUNDS: dict[str, tuple[str, str]] = {
    "ARTIKEL_SPRINT": ("A1", "B2"),
    "QUICK_MIX_A1A2": ("A1", "B2"),
}
