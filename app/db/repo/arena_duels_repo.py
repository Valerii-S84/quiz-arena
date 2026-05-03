from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_sessions import QuizSession
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_ROLE_CHALLENGER,
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_DUEL_STATUS_DRAFT,
    ARENA_DUEL_STATUS_EXPIRED,
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
    async def get_source_friend_duel_with_baseline_for_update(
        session: AsyncSession,
        *,
        source_friend_challenge_id: UUID,
    ) -> ArenaActiveDuelRow | None:
        stmt = (
            select(ArenaDuel, ArenaAttempt)
            .join(
                ArenaAttempt,
                and_(
                    ArenaAttempt.arena_duel_id == ArenaDuel.id,
                    ArenaAttempt.id == ArenaDuel.baseline_attempt_id,
                ),
            )
            .where(ArenaDuel.source_friend_challenge_id == source_friend_challenge_id)
            .where(
                ArenaAttempt.score.is_not(None),
                ArenaAttempt.time_ms.is_not(None),
                ArenaAttempt.completed_at.is_not(None),
            )
            .order_by(ArenaDuel.created_at.desc(), ArenaDuel.id.desc())
            .limit(1)
            .with_for_update(of=(ArenaDuel, ArenaAttempt))
        )
        result = await session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            return None
        duel, baseline_attempt = row.t
        return ArenaActiveDuelRow(duel=duel, baseline_attempt=baseline_attempt)

    @staticmethod
    async def expire_active_duels(session: AsyncSession, *, now_utc: datetime) -> int:
        stmt = (
            update(ArenaDuel)
            .where(
                ArenaDuel.status == ARENA_DUEL_STATUS_ACTIVE,
                ArenaDuel.expires_at <= now_utc,
            )
            .values(status=ARENA_DUEL_STATUS_EXPIRED, updated_at=now_utc)
        )
        result = await session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    @staticmethod
    async def expire_draft_duels(session: AsyncSession, *, now_utc: datetime) -> int:
        stmt = (
            update(ArenaDuel)
            .where(
                ArenaDuel.status == ARENA_DUEL_STATUS_DRAFT,
                ArenaDuel.expires_at <= now_utc,
            )
            .values(status=ARENA_DUEL_STATUS_EXPIRED, updated_at=now_utc)
        )
        result = await session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    @staticmethod
    async def count_creator_duels_by_access_type(
        session: AsyncSession,
        *,
        creator_user_id: int,
        access_type: str,
        since: datetime | None = None,
    ) -> int:
        stmt = select(func.count(ArenaDuel.id)).where(
            ArenaDuel.creator_user_id == creator_user_id,
            ArenaDuel.access_type == access_type,
            ArenaDuel.source_friend_challenge_id.is_(None),
        )
        if since is not None:
            stmt = stmt.where(ArenaDuel.created_at >= since)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_challenger_attempts_by_access_type(
        session: AsyncSession,
        *,
        user_id: int,
        access_type: str,
        since: datetime | None = None,
    ) -> int:
        stmt = select(func.count(ArenaAttempt.id)).where(
            ArenaAttempt.user_id == user_id,
            ArenaAttempt.role == ARENA_ATTEMPT_ROLE_CHALLENGER,
            ArenaAttempt.access_type == access_type,
        )
        if since is not None:
            stmt = stmt.where(ArenaAttempt.created_at >= since)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_paid_ticket_usage(session: AsyncSession, *, user_id: int) -> int:
        # Friend-published arena rows reuse the original friend challenge entitlement.
        duel_result = await session.execute(
            select(func.count(ArenaDuel.id)).where(
                ArenaDuel.creator_user_id == user_id,
                ArenaDuel.access_type == "PAID_TICKET",
                ArenaDuel.source_friend_challenge_id.is_(None),
            )
        )
        attempt_result = await session.execute(
            select(func.count(ArenaAttempt.id)).where(
                ArenaAttempt.user_id == user_id,
                ArenaAttempt.role == ARENA_ATTEMPT_ROLE_CHALLENGER,
                ArenaAttempt.access_type == "PAID_TICKET",
            )
        )
        return int(duel_result.scalar_one() or 0) + int(attempt_result.scalar_one() or 0)

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
    async def get_baseline_attempt(
        session: AsyncSession,
        *,
        duel: ArenaDuel,
    ) -> ArenaAttempt | None:
        if duel.baseline_attempt_id is None:
            return None
        attempt_stmt = select(ArenaAttempt).where(
            ArenaAttempt.arena_duel_id == duel.id,
            ArenaAttempt.id == duel.baseline_attempt_id,
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
