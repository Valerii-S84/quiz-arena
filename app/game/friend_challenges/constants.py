from __future__ import annotations

DUEL_TYPE_DIRECT = "DIRECT"
DUEL_TYPE_OPEN = "OPEN"

DUEL_STATUS_PENDING = "PENDING"
DUEL_STATUS_ACCEPTED = "ACCEPTED"
DUEL_STATUS_CREATOR_DONE = "CREATOR_DONE"
DUEL_STATUS_OPPONENT_DONE = "OPPONENT_DONE"
DUEL_STATUS_COMPLETED = "COMPLETED"
DUEL_STATUS_EXPIRED = "EXPIRED"
DUEL_STATUS_CANCELED = "CANCELED"
DUEL_STATUS_WALKOVER = "WALKOVER"

# Transitional compatibility for pre-v2 rows that were not migrated yet.
DUEL_STATUS_LEGACY_ACTIVE = "ACTIVE"

DUEL_ACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        DUEL_STATUS_PENDING,
        DUEL_STATUS_ACCEPTED,
        DUEL_STATUS_CREATOR_DONE,
        DUEL_STATUS_OPPONENT_DONE,
        DUEL_STATUS_LEGACY_ACTIVE,
    }
)

DUEL_PLAYABLE_STATUSES: frozenset[str] = frozenset(
    {
        DUEL_STATUS_ACCEPTED,
        DUEL_STATUS_CREATOR_DONE,
        DUEL_STATUS_OPPONENT_DONE,
        DUEL_STATUS_LEGACY_ACTIVE,
    }
)

DUEL_FINISHED_STATUSES: frozenset[str] = frozenset(
    {
        DUEL_STATUS_COMPLETED,
        DUEL_STATUS_EXPIRED,
        DUEL_STATUS_CANCELED,
        DUEL_STATUS_WALKOVER,
    }
)


def normalize_duel_status(*, status: str, has_opponent: bool) -> str:
    if status != DUEL_STATUS_LEGACY_ACTIVE:
        return status
    return DUEL_STATUS_ACCEPTED if has_opponent else DUEL_STATUS_PENDING


def is_duel_active_status(status: str) -> bool:
    return status in DUEL_ACTIVE_STATUSES


def is_duel_playable_status(status: str) -> bool:
    return status in DUEL_PLAYABLE_STATUSES
