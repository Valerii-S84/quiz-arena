from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.game.sessions.types import StartSessionResult


@dataclass(frozen=True, slots=True)
class ArenaDuelSnapshot:
    duel_id: UUID
    creator_user_id: int
    mode_code: str
    status: str
    question_ids: tuple[str, ...]
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    baseline_attempt_id: UUID | None = None
    baseline_score: int | None = None
    baseline_time_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ArenaBaselineStartResult:
    duel: ArenaDuelSnapshot
    baseline_attempt_id: UUID
    start_result: StartSessionResult


@dataclass(frozen=True, slots=True)
class ArenaChallengerStartResult:
    duel: ArenaDuelSnapshot
    challenger_attempt_id: UUID
    start_result: StartSessionResult


@dataclass(frozen=True, slots=True)
class ArenaActiveDuelSnapshot:
    duel_id: UUID
    creator_user_id: int
    mode_code: str
    question_ids: tuple[str, ...]
    baseline_attempt_id: UUID
    score: int
    time_ms: int
    expires_at: datetime
