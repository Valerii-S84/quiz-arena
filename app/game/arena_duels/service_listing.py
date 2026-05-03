from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.arena_duels_repo import ArenaDuelsRepo
from app.game.arena_duels.constants import ARENA_DEFAULT_ACTIVE_LIST_LIMIT
from app.game.arena_duels.service_common import build_active_duel_snapshot, get_current_best_attempt
from app.game.arena_duels.types import ArenaActiveDuelSnapshot


async def list_active_arena_duels(
    session: AsyncSession,
    *,
    now_utc: datetime,
    limit: int = ARENA_DEFAULT_ACTIVE_LIST_LIMIT,
) -> tuple[ArenaActiveDuelSnapshot, ...]:
    rows = await ArenaDuelsRepo.list_active_with_baseline(
        session,
        now_utc=now_utc,
        limit=limit,
    )
    snapshots: list[ArenaActiveDuelSnapshot] = []
    for row in rows:
        current_best_attempt = await get_current_best_attempt(session, duel_id=row.duel.id)
        if current_best_attempt is None:
            continue
        snapshot = build_active_duel_snapshot(
            row,
            current_best_attempt=current_best_attempt,
        )
        if snapshot is not None:
            snapshots.append(snapshot)
    return tuple(snapshots)
