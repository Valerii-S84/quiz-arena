from __future__ import annotations

from dataclasses import dataclass

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel


@dataclass(frozen=True, slots=True)
class ArenaAttemptDuelContext:
    attempt: ArenaAttempt
    duel: ArenaDuel


@dataclass(frozen=True, slots=True)
class ArenaAttemptCompletionSummary:
    completed_rounds: int
    score: int
    time_ms: int


@dataclass(frozen=True, slots=True)
class ArenaActiveDuelRow:
    duel: ArenaDuel
    baseline_attempt: ArenaAttempt


@dataclass(frozen=True, slots=True)
class ArenaDuelAcceptContext:
    duel: ArenaDuel
    existing_attempt: ArenaAttempt | None
