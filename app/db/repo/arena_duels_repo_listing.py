from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_ACTIVE,
)

from .arena_duels_repo_models import ArenaActiveDuelRow


class ArenaDuelsRepoListingMixin:
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
