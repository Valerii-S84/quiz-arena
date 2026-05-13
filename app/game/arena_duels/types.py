from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
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
class ArenaBeatenNotification:
    arena_duel_id: UUID
    previous_best_attempt_id: UUID
    previous_best_user_id: int
    previous_best_score: int
    previous_best_time_ms: int
    new_best_attempt_id: UUID
    new_best_user_id: int
    new_best_score: int
    new_best_time_ms: int
    notification_type: str


@dataclass(frozen=True, slots=True)
class ArenaAttemptCompletionResult:
    duel: ArenaDuelSnapshot
    beaten_notification: ArenaBeatenNotification | None = None
    completed_attempt: ArenaAttemptResultLine | None = None
    opponent_attempt: ArenaAttemptResultLine | None = None


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


@dataclass(frozen=True, slots=True)
class ArenaAttemptResultLine:
    user_id: int
    score: int
    time_ms: int
    result: str | None
    attempt_id: UUID | None = None
