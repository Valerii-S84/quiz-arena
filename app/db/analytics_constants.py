from __future__ import annotations

DAILY_CUP_UNIQUE_PUSH_EVENT_TYPES: tuple[str, ...] = (
    "daily_cup_invite_registration_push_sent",
    "daily_cup_last_call_reminder_sent",
    "daily_cup_prestart_reminder_sent",
)
DAILY_CUP_UNIQUE_PUSH_EVENT_TYPES_SQL = ",".join(
    f"'{event_type}'" for event_type in DAILY_CUP_UNIQUE_PUSH_EVENT_TYPES
)


__all__ = [
    "DAILY_CUP_UNIQUE_PUSH_EVENT_TYPES",
    "DAILY_CUP_UNIQUE_PUSH_EVENT_TYPES_SQL",
]
