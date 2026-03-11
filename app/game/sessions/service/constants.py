from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings

FRIEND_CHALLENGE_TOTAL_ROUNDS = 12
FRIEND_CHALLENGE_FREE_CREATES = 2
FRIEND_CHALLENGE_TICKET_PRODUCT_CODE = "FRIEND_CHALLENGE_5"
DUEL_PENDING_TTL_SECONDS = max(60, int(get_settings().duel_pending_ttl_hours) * 3600)
DUEL_ACCEPTED_TTL_SECONDS = max(60, int(get_settings().duel_accepted_ttl_hours) * 3600)
DUEL_MAX_ACTIVE_PER_USER = max(1, int(get_settings().duel_max_active_per_user))
DUEL_MAX_NEW_PER_DAY = max(1, int(get_settings().duel_max_new_per_day))
DUEL_MAX_PUSH_PER_USER = max(1, int(get_settings().duel_max_push_per_user))
# Backward-compatible alias used in older modules/tests.
FRIEND_CHALLENGE_TTL_SECONDS = DUEL_ACCEPTED_TTL_SECONDS
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
PERSISTENT_ADAPTIVE_LEVEL_CHAIN: tuple[str, ...] = ("A1", "A2", "B1", "B2")
MIX_STEP_WEIGHTS: dict[int, float] = {
    1: 0.25,
    2: 0.50,
    3: 0.75,
}
PROGRESSION_WARM_UP_THRESHOLD = 30
PROGRESSION_ACCURACY_THRESHOLD = 0.75
PROGRESSION_CORRECT_PER_STEP = 10


@dataclass(frozen=True, slots=True)
class ModeProgressionConfig:
    warm_up_threshold: int
    accuracy_threshold: float
    correct_per_step: int


DEFAULT_MODE_PROGRESSION_CONFIG = ModeProgressionConfig(
    warm_up_threshold=PROGRESSION_WARM_UP_THRESHOLD,
    accuracy_threshold=PROGRESSION_ACCURACY_THRESHOLD,
    correct_per_step=PROGRESSION_CORRECT_PER_STEP,
)
MODE_PROGRESSION_CONFIGS: dict[str, ModeProgressionConfig] = {
    mode_code: DEFAULT_MODE_PROGRESSION_CONFIG for mode_code in PERSISTENT_ADAPTIVE_MODE_BOUNDS
}
