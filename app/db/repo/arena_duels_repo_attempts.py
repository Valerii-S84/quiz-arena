from __future__ import annotations

from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_sessions import QuizSession
from app.game.arena_duels.constants import ARENA_SOURCE

from .arena_duels_repo_models import ArenaAttemptCompletionSummary, ArenaAttemptDuelContext


class ArenaDuelsRepoAttemptsMixin:
    @staticmethod
    async def get_attempt_duel_for_update(
        session: AsyncSession,
        *,
        attempt_id: UUID,
    ) -> ArenaAttemptDuelContext | None:
        stmt = (
            select(ArenaAttempt, ArenaDuel)
            .join(ArenaDuel, ArenaDuel.id == ArenaAttempt.arena_duel_id)
            .where(ArenaAttempt.id == attempt_id)
            .with_for_update(of=(ArenaAttempt, ArenaDuel))
        )
        result = await session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            return None
        attempt, duel = row.t
        return ArenaAttemptDuelContext(attempt=attempt, duel=duel)

    @staticmethod
    async def summarize_completed_attempt(
        session: AsyncSession,
        *,
        attempt_id: UUID,
    ) -> ArenaAttemptCompletionSummary:
        first_round_attempts = _build_first_round_attempts_subquery(attempt_id)
        correct_count = func.coalesce(
            func.sum(case((first_round_attempts.c.is_correct.is_(True), 1), else_=0)),
            0,
        )
        total_time_ms = func.coalesce(func.sum(first_round_attempts.c.response_ms), 0)
        stmt = (
            select(func.count(first_round_attempts.c.arena_round), correct_count, total_time_ms)
            .select_from(first_round_attempts)
            .where(first_round_attempts.c.attempt_rank == 1)
        )
        result = await session.execute(stmt)
        completed_rounds, score, time_ms = result.one()
        return ArenaAttemptCompletionSummary(
            completed_rounds=max(0, int(completed_rounds or 0)),
            score=max(0, int(score or 0)),
            time_ms=max(0, int(time_ms or 0)),
        )

    @staticmethod
    async def list_completed_attempts_for_duel(
        session: AsyncSession,
        *,
        duel_id: UUID,
        exclude_attempt_id: UUID | None = None,
    ) -> list[ArenaAttempt]:
        stmt = (
            select(ArenaAttempt)
            .where(
                ArenaAttempt.arena_duel_id == duel_id,
                ArenaAttempt.completed_at.is_not(None),
                ArenaAttempt.score.is_not(None),
                ArenaAttempt.time_ms.is_not(None),
            )
            .order_by(
                ArenaAttempt.score.desc(),
                ArenaAttempt.time_ms.asc(),
                ArenaAttempt.completed_at.asc(),
                ArenaAttempt.id.asc(),
            )
        )
        if exclude_attempt_id is not None:
            stmt = stmt.where(ArenaAttempt.id != exclude_attempt_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def has_completed_attempt_for_user(
        session: AsyncSession,
        *,
        duel_id: UUID,
        user_id: int,
    ) -> bool:
        stmt = (
            select(ArenaAttempt.id)
            .where(
                ArenaAttempt.arena_duel_id == duel_id,
                ArenaAttempt.user_id == user_id,
                ArenaAttempt.completed_at.is_not(None),
                ArenaAttempt.score.is_not(None),
                ArenaAttempt.time_ms.is_not(None),
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None


def _build_first_round_attempts_subquery(attempt_id: UUID):
    return (
        select(
            QuizSession.arena_round.label("arena_round"),
            QuizAttempt.is_correct.label("is_correct"),
            QuizAttempt.response_ms.label("response_ms"),
            func.row_number()
            .over(
                partition_by=QuizSession.arena_round,
                order_by=(QuizAttempt.answered_at.asc(), QuizAttempt.id.asc()),
            )
            .label("attempt_rank"),
        )
        .select_from(QuizSession)
        .join(QuizAttempt, QuizAttempt.session_id == QuizSession.id)
        .where(
            QuizSession.source == ARENA_SOURCE,
            QuizSession.arena_attempt_id == attempt_id,
            QuizSession.arena_round.is_not(None),
            QuizSession.status == "COMPLETED",
            QuizSession.completed_at.is_not(None),
        )
        .subquery()
    )
