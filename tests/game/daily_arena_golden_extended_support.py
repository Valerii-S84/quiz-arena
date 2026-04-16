from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from tests.game.daily_arena_golden_support import status_tournament
from tests.type_helpers import AsyncSessionStub


class DailyArenaExtendedSession(AsyncSessionStub):
    pass


def arena_tournament(*, status: str, current_round: int = 0) -> SimpleNamespace:
    tournament = status_tournament(status=status, current_round=current_round)
    tournament.round_deadline = datetime(2026, 3, 1, 18, 30, tzinfo=UTC)
    return tournament


def empty_daily_cup_result() -> dict[str, int]:
    return {"processed": 0, "participants_total": 0, "sent": 0, "edited": 0, "failed": 0}
