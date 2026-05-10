from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.tournaments import Tournament
from app.game.tournaments.constants import (
    TOURNAMENT_FORMAT_QUICK_5,
    TOURNAMENT_MATCH_STATUS_PENDING,
    TOURNAMENT_STATUS_REGISTRATION,
    TOURNAMENT_TYPE_PRIVATE,
)
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)


class TournamentSession(AsyncSessionStub):
    pass


def async_return(value: object):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def tournament_row(**overrides: object) -> Tournament:
    tournament_id = cast(UUID, overrides.pop("id", uuid4()))
    payload: dict[str, object] = {
        "id": tournament_id,
        "type": TOURNAMENT_TYPE_PRIVATE,
        "created_by": 11,
        "name": "Arena",
        "status": TOURNAMENT_STATUS_REGISTRATION,
        "format": TOURNAMENT_FORMAT_QUICK_5,
        "max_participants": 4,
        "current_round": 0,
        "registration_deadline": NOW_UTC + timedelta(hours=1),
        "round_deadline": None,
        "invite_code": "invite-code",
        "created_at": NOW_UTC,
    }
    payload.update(overrides)
    return Tournament(**payload)


def participant_row(
    *,
    tournament_id: UUID,
    user_id: int,
    score: str = "0",
) -> TournamentParticipant:
    return TournamentParticipant(
        tournament_id=tournament_id,
        user_id=user_id,
        score=Decimal(score),
        tie_break=Decimal(score),
        joined_at=NOW_UTC,
    )


def match_row(
    *,
    tournament_id: UUID | None = None,
    user_a: int = 11,
    user_b: int | None = 22,
    status: str = TOURNAMENT_MATCH_STATUS_PENDING,
    challenge_id: UUID | None = None,
) -> TournamentMatch:
    return TournamentMatch(
        id=uuid4(),
        tournament_id=tournament_id or uuid4(),
        round_no=1,
        user_a=user_a,
        user_b=user_b,
        friend_challenge_id=challenge_id,
        status=status,
        winner_id=None,
        deadline=NOW_UTC,
    )
