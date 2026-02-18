from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.reconciliation_runs import ReconciliationRun


class ReconciliationRunsRepo:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        started_at: datetime,
        finished_at: datetime | None,
        status: str,
        diff_count: int,
    ) -> ReconciliationRun:
        run = ReconciliationRun(
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            diff_count=diff_count,
        )
        session.add(run)
        await session.flush()
        return run
