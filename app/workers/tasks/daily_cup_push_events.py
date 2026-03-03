from __future__ import annotations

from uuid import UUID

from app.core.analytics_events import EVENT_SOURCE_WORKER, emit_analytics_event
from app.db.repo.analytics_repo import AnalyticsRepo
from app.db.session import SessionLocal


async def list_already_pushed_user_ids(
    *,
    event_type: str,
    tournament_id: str,
    user_ids: list[int],
) -> set[int]:
    async with SessionLocal.begin() as session:
        return await AnalyticsRepo.list_user_ids_by_event_type_and_tournament(
            session,
            event_type=event_type,
            tournament_id=tournament_id,
            user_ids=user_ids,
        )


async def store_push_sent_events(
    *,
    event_type: str,
    tournament_id: UUID,
    user_ids: list[int],
    happened_at,
) -> None:
    if not user_ids:
        return
    payload: dict[str, object] = {"tournament_id": str(tournament_id)}
    async with SessionLocal.begin() as session:
        for user_id in user_ids:
            await emit_analytics_event(
                session,
                event_type=event_type,
                source=EVENT_SOURCE_WORKER,
                happened_at=happened_at,
                user_id=user_id,
                payload=payload,
            )
