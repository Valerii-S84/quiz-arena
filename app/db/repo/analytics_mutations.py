from __future__ import annotations

from app.db.repo.analytics_daily_mutations import upsert_daily
from app.db.repo.analytics_event_mutations import (
    create_arena_beaten_notification_event_once,
    create_arena_revanche_event_once,
    create_daily_cup_push_event_once,
    create_event,
    delete_arena_revanche_events,
)
from app.db.repo.analytics_lock_mutations import (
    lock_arena_beaten_notification_event_key,
    lock_arena_revanche_event_key,
    lock_arena_revanche_sender_quota,
)
from app.db.repo.analytics_retention_mutations import delete_events_created_before

__all__ = [
    "create_arena_beaten_notification_event_once",
    "create_arena_revanche_event_once",
    "create_daily_cup_push_event_once",
    "create_event",
    "delete_arena_revanche_events",
    "delete_events_created_before",
    "lock_arena_beaten_notification_event_key",
    "lock_arena_revanche_event_key",
    "lock_arena_revanche_sender_quota",
    "upsert_daily",
]
