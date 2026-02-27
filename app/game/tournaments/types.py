from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(slots=True)
class TournamentSnapshot:
    tournament_id: UUID
    type: str
    created_by: int | None
    name: str | None
    status: str
    format: str
    max_participants: int
    current_round: int
    registration_deadline: datetime
    round_deadline: datetime | None
    invite_code: str
    created_at: datetime


@dataclass(slots=True)
class TournamentJoinResult:
    snapshot: TournamentSnapshot
    joined_now: bool
    participants_total: int


@dataclass(slots=True)
class TournamentStartResult:
    snapshot: TournamentSnapshot
    round_no: int
    matches_total: int


@dataclass(slots=True)
class SwissParticipant:
    user_id: int
    score: Decimal
    tie_break: Decimal
    joined_at: datetime


@dataclass(slots=True)
class SwissPair:
    user_a: int
    user_b: int | None


@dataclass(slots=True)
class TournamentParticipantSnapshot:
    tournament_id: UUID
    user_id: int
    score: Decimal
    tie_break: Decimal
    joined_at: datetime


@dataclass(slots=True)
class TournamentLobbySnapshot:
    tournament: TournamentSnapshot
    participants: tuple[TournamentParticipantSnapshot, ...]
    viewer_joined: bool
    viewer_is_creator: bool
    can_start: bool
    viewer_current_match_challenge_id: UUID | None
    viewer_current_opponent_user_id: int | None
