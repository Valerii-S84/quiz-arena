from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournament_round_scores import TournamentRoundScore


@dataclass(frozen=True, slots=True)
class TournamentRoundScorePayload:
    tournament_id: UUID
    round_number: int
    player_id: int
    opponent_id: int | None
    wins: int
    is_draw: bool
    correct_answers: int
    total_time_ms: int
    got_bye: bool
    auto_finished: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TournamentStandingAggregate:
    player_id: int
    wins: int
    correct_answers: int
    total_time_ms: int


class TournamentRoundScoresRepo:
    @staticmethod
    async def upsert_result(
        session: AsyncSession,
        *,
        payload: TournamentRoundScorePayload,
    ) -> None:
        stmt = (
            insert(TournamentRoundScore)
            .values(
                id=uuid4(),
                tournament_id=payload.tournament_id,
                round_number=payload.round_number,
                player_id=payload.player_id,
                opponent_id=payload.opponent_id,
                wins=payload.wins,
                is_draw=payload.is_draw,
                correct_answers=payload.correct_answers,
                total_time_ms=payload.total_time_ms,
                got_bye=payload.got_bye,
                auto_finished=payload.auto_finished,
                created_at=payload.created_at,
            )
            .on_conflict_do_update(
                index_elements=[
                    TournamentRoundScore.tournament_id,
                    TournamentRoundScore.round_number,
                    TournamentRoundScore.player_id,
                ],
                set_={
                    "opponent_id": payload.opponent_id,
                    "wins": payload.wins,
                    "is_draw": payload.is_draw,
                    "correct_answers": payload.correct_answers,
                    "total_time_ms": payload.total_time_ms,
                    "got_bye": payload.got_bye,
                    "auto_finished": payload.auto_finished,
                    "created_at": payload.created_at,
                },
            )
        )
        await session.execute(stmt)

    @staticmethod
    async def list_standings_aggregates(
        session: AsyncSession,
        *,
        tournament_id: UUID,
    ) -> list[TournamentStandingAggregate]:
        stmt = (
            select(
                TournamentRoundScore.player_id,
                func.coalesce(func.sum(TournamentRoundScore.wins), 0),
                func.coalesce(func.sum(TournamentRoundScore.correct_answers), 0),
                func.coalesce(func.sum(TournamentRoundScore.total_time_ms), 0),
            )
            .where(TournamentRoundScore.tournament_id == tournament_id)
            .group_by(TournamentRoundScore.player_id)
        )
        result = await session.execute(stmt)
        return [
            TournamentStandingAggregate(
                player_id=int(player_id),
                wins=int(wins),
                correct_answers=int(correct_answers),
                total_time_ms=int(total_time_ms),
            )
            for player_id, wins, correct_answers, total_time_ms in result.all()
        ]
