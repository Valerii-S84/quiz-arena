from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.db.repo.tournament_round_scores_repo import (
    TournamentRoundScorePayload,
    TournamentRoundScoresRepo,
    TournamentStandingAggregate,
)
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult

UTC = timezone.utc


class _OneResult:
    def __init__(self, row: tuple[object, object]) -> None:
        self._row = row

    def one(self) -> tuple[object, object]:
        return self._row


def _payload() -> TournamentRoundScorePayload:
    return TournamentRoundScorePayload(
        tournament_id=uuid4(),
        round_number=2,
        player_id=10,
        opponent_id=20,
        wins=2,
        is_draw=False,
        correct_answers=6,
        total_time_ms=45000,
        got_bye=False,
        auto_finished=True,
        created_at=datetime(2026, 3, 14, 12, 0, tzinfo=UTC),
    )


async def test_upsert_result_uses_tournament_round_player_conflict_key() -> None:
    session = RecordingSession(_RowsResult([]))

    await TournamentRoundScoresRepo.upsert_result(session, payload=_payload())

    sql = compile_statement(session.statement)
    assert "INSERT INTO tournament_round_scores" in sql
    assert "ON CONFLICT (tournament_id, round_number, player_id) DO UPDATE" in sql
    assert "wins = %(param_" in sql
    assert "auto_finished = %(param_" in sql


async def test_list_standings_aggregates_maps_numeric_rows() -> None:
    tournament_id = uuid4()
    session = RecordingSession(_RowsResult([(10, "2", "11", "90000")]))

    rows = await TournamentRoundScoresRepo.list_standings_aggregates(
        session,
        tournament_id=tournament_id,
    )

    assert rows == [
        TournamentStandingAggregate(
            player_id=10,
            wins=2,
            correct_answers=11,
            total_time_ms=90000,
        )
    ]
    sql = compile_statement(session.statement)
    assert "sum(tournament_round_scores.wins)" in sql
    assert "GROUP BY tournament_round_scores.player_id" in sql


async def test_aggregate_player_totals_defaults_null_sums_to_zero_decimals() -> None:
    tournament_id = uuid4()
    session = RecordingSession(_OneResult((None, None)))

    score, tie_break = await TournamentRoundScoresRepo.aggregate_player_totals(
        session,
        player_id=10,
        tournament_id=tournament_id,
    )

    assert score == Decimal("0")
    assert tie_break == Decimal("0")
    sql = compile_statement(session.statement)
    assert "tournament_round_scores.player_id = 10" in sql
    assert str(tournament_id) in sql
