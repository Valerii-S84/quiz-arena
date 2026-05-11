from __future__ import annotations

from app.db.repo.analytics_arena_event_mutations import (
    create_arena_beaten_notification_event_once,
    create_arena_revanche_event_once,
    delete_arena_revanche_events,
)
from app.db.repo.analytics_daily_cup_push_mutations import create_daily_cup_push_event_once
from app.db.repo.analytics_event_core_mutations import create_event

__all__ = [
    "create_arena_beaten_notification_event_once",
    "create_arena_revanche_event_once",
    "create_daily_cup_push_event_once",
    "create_event",
    "delete_arena_revanche_events",
]
