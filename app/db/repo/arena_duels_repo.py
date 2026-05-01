from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_sessions import QuizSession
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_SOURCE,
)


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


class ArenaDuelsRepo:
    @staticmethod
    async def create_duel(session: AsyncSession, *, duel: ArenaDuel) -> ArenaDuel:
        session.add(duel)
        await session.flush()
        return duel

    @staticmethod
    async def create_attempt(session: AsyncSession, *, attempt: ArenaAttempt) -> ArenaAttempt:
        session.add(attempt)
        await session.flush()
        return attempt

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
    async def get_accept_context_for_update(
        session: AsyncSession,
        *,
        duel_id: UUID,
        user_id: int,
    ) -> ArenaDuelAcceptContext | None:
        existing_context = await ArenaDuelsRepo._get_existing_accept_context_for_update(
            session,
            duel_id=duel_id,
            user_id=user_id,
        )
        if existing_context is not None:
            return existing_context

        duel = await ArenaDuelsRepo._get_duel_for_update(session, duel_id=duel_id)
        if duel is None:
            return None

        existing_attempt = await ArenaDuelsRepo._get_existing_attempt(
            session,
            duel_id=duel_id,
            user_id=user_id,
        )
        return ArenaDuelAcceptContext(duel=duel, existing_attempt=existing_attempt)

    @staticmethod
    async def _get_existing_accept_context_for_update(
        session: AsyncSession,
        *,
        duel_id: UUID,
        user_id: int,
    ) -> ArenaDuelAcceptContext | None:
        stmt = (
            select(ArenaAttempt, ArenaDuel)
            .join(ArenaDuel, ArenaDuel.id == ArenaAttempt.arena_duel_id)
            .where(
                ArenaAttempt.arena_duel_id == duel_id,
                ArenaAttempt.user_id == user_id,
            )
            .with_for_update(of=(ArenaAttempt, ArenaDuel))
        )
        result = await session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            return None
        attempt, duel = row.t
        return ArenaDuelAcceptContext(duel=duel, existing_attempt=attempt)

    @staticmethod
    async def _get_duel_for_update(
        session: AsyncSession,
        *,
        duel_id: UUID,
    ) -> ArenaDuel | None:
        duel_stmt = select(ArenaDuel).where(ArenaDuel.id == duel_id).with_for_update()
        duel_result = await session.execute(duel_stmt)
        return duel_result.scalar_one_or_none()

    @staticmethod
    async def _get_existing_attempt(
        session: AsyncSession,
        *,
        duel_id: UUID,
        user_id: int,
    ) -> ArenaAttempt | None:
        attempt_stmt = select(ArenaAttempt).where(
            ArenaAttempt.arena_duel_id == duel_id,
            ArenaAttempt.user_id == user_id,
        )
        attempt_result = await session.execute(attempt_stmt)
        return attempt_result.scalar_one_or_none()

    @staticmethod
    async def summarize_completed_attempt(
        session: AsyncSession,
        *,
        attempt_id: UUID,
    ) -> ArenaAttemptCompletionSummary:
        first_round_attempts = (
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
    async def list_active_with_baseline(
        session: AsyncSession,
        *,
        now_utc: datetime,
        limit: int,
    ) -> list[ArenaActiveDuelRow]:
        resolved_limit = max(1, int(limit))
        stmt = (
            select(ArenaDuel, ArenaAttempt)
            .join(
                ArenaAttempt,
                and_(
                    ArenaAttempt.arena_duel_id == ArenaDuel.id,
                    ArenaAttempt.id == ArenaDuel.baseline_attempt_id,
                ),
            )
            .where(
                ArenaDuel.status == ARENA_DUEL_STATUS_ACTIVE,
                ArenaDuel.expires_at > now_utc,
                ArenaDuel.baseline_attempt_id.is_not(None),
                ArenaDuel.question_ids.is_not(None),
                ArenaAttempt.role == ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
                ArenaAttempt.score.is_not(None),
                ArenaAttempt.time_ms.is_not(None),
                ArenaAttempt.completed_at.is_not(None),
            )
            .order_by(ArenaDuel.created_at.desc(), ArenaDuel.id.desc())
            .limit(resolved_limit)
        )
        result = await session.execute(stmt)
        rows: list[ArenaActiveDuelRow] = []
        for row in result.all():
            duel, baseline_attempt = row.t
            rows.append(ArenaActiveDuelRow(duel=duel, baseline_attempt=baseline_attempt))
        return rows
