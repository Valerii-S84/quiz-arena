from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event

ARENA_EVENT_DUEL_MENU_OPENED = "duel_menu_opened"
ARENA_EVENT_DUEL_MODE_SELECTED = "duel_mode_selected"
ARENA_EVENT_ARENA_OPENED = "arena_opened"
ARENA_EVENT_ARENA_DUEL_CREATED = "arena_duel_created"
ARENA_EVENT_ARENA_DUEL_STARTED = "arena_duel_started"
ARENA_EVENT_ARENA_DUEL_COMPLETED = "arena_duel_completed"
ARENA_EVENT_ARENA_DUEL_PUBLISHED = "arena_duel_published"
ARENA_EVENT_ARENA_DUEL_ACCEPTED = "arena_duel_accepted"
ARENA_EVENT_ARENA_RESULT_SHOWN = "arena_result_shown"
ARENA_EVENT_FRIEND_DUEL_OPENED = "friend_duel_opened"
ARENA_EVENT_FRIEND_DUEL_PUBLISHED_TO_ARENA = "friend_duel_published_to_arena"
ARENA_EVENT_DUEL_LIMIT_HIT = "duel_limit_hit"
ARENA_EVENT_DUEL_PAYWALL_SHOWN = "duel_paywall_shown"
ARENA_EVENT_DUEL_TICKET_CLICKED = "duel_ticket_clicked"
ARENA_EVENT_PREMIUM_WEEK_CLICKED = "premium_week_clicked"


def build_arena_event_payload(
    *,
    user_id: int | None = None,
    friend_challenge_id: UUID | str | None = None,
    arena_duel_id: UUID | str | None = None,
    attempt_id: UUID | str | None = None,
    action: str | None = None,
    access_type: str | None = None,
    result: str | None = None,
    score: int | None = None,
    time_ms: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {}
    if user_id is not None:
        payload["user_id"] = int(user_id)
    if friend_challenge_id is not None:
        payload["friend_challenge_id"] = str(friend_challenge_id)
    if arena_duel_id is not None:
        payload["arena_duel_id"] = str(arena_duel_id)
    if attempt_id is not None:
        payload["attempt_id"] = str(attempt_id)
    if action is not None:
        payload["action"] = action
    if access_type is not None:
        payload["access_type"] = access_type
    if result is not None:
        payload["result"] = result
    if score is not None:
        payload["score"] = int(score)
    if time_ms is not None:
        payload["time_ms"] = int(time_ms)
    return payload


async def emit_arena_analytics_event(
    session,
    *,
    event_type: str,
    happened_at: datetime,
    user_id: int | None = None,
    payload: dict[str, object] | None = None,
    source: str = EVENT_SOURCE_BOT,
) -> None:
    execute = getattr(session, "execute", None)
    if not callable(execute):
        return
    await emit_analytics_event(
        session,
        event_type=event_type,
        source=source,
        happened_at=happened_at,
        user_id=user_id,
        payload=payload or {},
    )


__all__ = [
    "ARENA_EVENT_ARENA_DUEL_ACCEPTED",
    "ARENA_EVENT_ARENA_DUEL_COMPLETED",
    "ARENA_EVENT_ARENA_DUEL_CREATED",
    "ARENA_EVENT_ARENA_DUEL_PUBLISHED",
    "ARENA_EVENT_ARENA_DUEL_STARTED",
    "ARENA_EVENT_ARENA_OPENED",
    "ARENA_EVENT_ARENA_RESULT_SHOWN",
    "ARENA_EVENT_DUEL_LIMIT_HIT",
    "ARENA_EVENT_DUEL_MENU_OPENED",
    "ARENA_EVENT_DUEL_MODE_SELECTED",
    "ARENA_EVENT_DUEL_PAYWALL_SHOWN",
    "ARENA_EVENT_DUEL_TICKET_CLICKED",
    "ARENA_EVENT_FRIEND_DUEL_OPENED",
    "ARENA_EVENT_FRIEND_DUEL_PUBLISHED_TO_ARENA",
    "ARENA_EVENT_PREMIUM_WEEK_CLICKED",
    "build_arena_event_payload",
    "emit_arena_analytics_event",
]
