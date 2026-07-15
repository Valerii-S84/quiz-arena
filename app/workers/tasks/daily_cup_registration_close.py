from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.game.tournaments.constants import (
    TOURNAMENT_STATUS_CANCELED,
    TOURNAMENT_STATUS_REGISTRATION,
)

_CLOSEABLE_STATUSES = {
    TOURNAMENT_STATUS_REGISTRATION,
    TOURNAMENT_STATUS_CANCELED,
}


@dataclass(frozen=True, slots=True)
class DailyCupCloseTransition:
    tournament_id: str
    canceled_telegram_targets: list[int]
    started_tournament_id: str | None
    events: list[dict[str, object]]
    participants_total: int
    canceled: int
    started: int


@dataclass(frozen=True, slots=True)
class DailyCupRegistrationCloseDependencies:
    list_participants_for_update: Callable[..., Awaitable[list[Any]]]
    list_users_by_ids: Callable[..., Awaitable[list[Any]]]
    start_round_one: Callable[..., Awaitable[None]]


async def build_close_transition(
    *,
    session: Any,
    tournament: Any,
    now_utc_value: datetime,
    minimum_participants: int,
    dependencies: DailyCupRegistrationCloseDependencies,
) -> DailyCupCloseTransition | None:
    if tournament.status not in _CLOSEABLE_STATUSES:
        return None
    participants = await dependencies.list_participants_for_update(
        session,
        tournament_id=tournament.id,
    )
    participants_total = len(participants)
    tournament_id = str(tournament.id)
    if tournament.status == TOURNAMENT_STATUS_CANCELED:
        return DailyCupCloseTransition(
            tournament_id=tournament_id,
            canceled_telegram_targets=await _cancellation_targets(
                session=session,
                participants=participants,
                list_users_by_ids=dependencies.list_users_by_ids,
            ),
            started_tournament_id=None,
            events=[],
            participants_total=participants_total,
            canceled=1,
            started=0,
        )
    if participants_total < minimum_participants:
        tournament.status = TOURNAMENT_STATUS_CANCELED
        tournament.round_deadline = None
        return DailyCupCloseTransition(
            tournament_id=tournament_id,
            canceled_telegram_targets=await _cancellation_targets(
                session=session,
                participants=participants,
                list_users_by_ids=dependencies.list_users_by_ids,
            ),
            started_tournament_id=None,
            events=[
                _canceled_event(tournament_id=tournament_id, participants_total=participants_total)
            ],
            participants_total=participants_total,
            canceled=1,
            started=0,
        )
    await dependencies.start_round_one(
        session,
        tournament=tournament,
        participants=participants,
        now_utc=now_utc_value,
    )
    return DailyCupCloseTransition(
        tournament_id=tournament_id,
        canceled_telegram_targets=[],
        started_tournament_id=tournament_id,
        events=_started_events(tournament_id=tournament_id, participants_total=participants_total),
        participants_total=participants_total,
        canceled=0,
        started=1,
    )


async def _cancellation_targets(
    *,
    session: Any,
    participants: list[Any],
    list_users_by_ids: Callable[..., Awaitable[list[Any]]],
) -> list[int]:
    users = await list_users_by_ids(session, [int(item.user_id) for item in participants])
    return [int(user.telegram_user_id) for user in users]


def _canceled_event(*, tournament_id: str, participants_total: int) -> dict[str, object]:
    return {
        "event_type": "daily_cup_canceled",
        "payload": {"tournament_id": tournament_id, "registered_total": participants_total},
    }


def _started_events(*, tournament_id: str, participants_total: int) -> list[dict[str, object]]:
    return [
        {
            "event_type": "daily_cup_started",
            "payload": {"tournament_id": tournament_id, "participants_total": participants_total},
        },
        {
            "event_type": "daily_cup_round_started",
            "payload": {"tournament_id": tournament_id, "round_no": 1},
        },
    ]
