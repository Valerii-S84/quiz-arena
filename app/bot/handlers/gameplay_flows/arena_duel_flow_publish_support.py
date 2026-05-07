from __future__ import annotations

from datetime import datetime
from typing import Any

from app.game.arena_duels.analytics import (
    ARENA_EVENT_ARENA_DUEL_PUBLISHED,
    ARENA_EVENT_FRIEND_DUEL_PUBLISHED_TO_ARENA,
    build_arena_event_payload,
)

from .arena_duel_flow_support import format_score_line


async def emit_friend_publish_events(
    *,
    session,
    emit_arena_analytics_event,
    user_id: int,
    friend_challenge_id,
    published_duel: object,
    now_utc: datetime,
) -> None:
    score = getattr(published_duel, "baseline_score", None)
    time_ms = getattr(published_duel, "baseline_time_ms", None)
    payload: dict[str, Any] = {
        "user_id": user_id,
        "friend_challenge_id": friend_challenge_id,
        "arena_duel_id": getattr(published_duel, "duel_id", None),
        "score": score if isinstance(score, int) else None,
        "time_ms": time_ms if isinstance(time_ms, int) else None,
    }
    await emit_arena_analytics_event(
        session,
        event_type=ARENA_EVENT_ARENA_DUEL_PUBLISHED,
        happened_at=now_utc,
        user_id=user_id,
        payload=build_arena_event_payload(action="publish_friend", **payload),
    )
    await emit_arena_analytics_event(
        session,
        event_type=ARENA_EVENT_FRIEND_DUEL_PUBLISHED_TO_ARENA,
        happened_at=now_utc,
        user_id=user_id,
        payload=build_arena_event_payload(**payload),
    )


def format_published_duel_score_line(published_duel: object | None) -> str | None:
    score = getattr(published_duel, "baseline_score", None)
    time_ms = getattr(published_duel, "baseline_time_ms", None)
    if not isinstance(score, int) or not isinstance(time_ms, int):
        return None
    return format_score_line(score=score, time_ms=time_ms)
