from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID


async def emit_daily_cup_events(
    *,
    now_utc_value: datetime,
    events: list[dict[str, object]],
    session_local: Any,
    emit_analytics_event: Callable[..., Any],
    event_source_worker: str,
) -> None:
    if not events:
        return
    async with session_local.begin() as session:
        for event in events:
            payload_raw = event.get("payload")
            await emit_analytics_event(
                session,
                event_type=str(event["event_type"]),
                source=event_source_worker,
                happened_at=now_utc_value,
                user_id=None,
                payload=(payload_raw if isinstance(payload_raw, dict) else {}),
            )


async def persist_daily_cup_standings_message_ids(
    *,
    tournament_id: UUID,
    new_message_ids: dict[int, int],
    replaced_message_ids: dict[int, int],
    session_local: Any,
    participants_repo: Any,
) -> None:
    if not new_message_ids and not replaced_message_ids:
        return
    async with session_local.begin() as session:
        for user_id, message_id in new_message_ids.items():
            await participants_repo.set_standings_message_id_if_missing(
                session,
                tournament_id=tournament_id,
                user_id=user_id,
                message_id=message_id,
            )
        for user_id, message_id in replaced_message_ids.items():
            await participants_repo.set_standings_message_id(
                session,
                tournament_id=tournament_id,
                user_id=user_id,
                message_id=message_id,
            )
