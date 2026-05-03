from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.arena_duels_repo import ArenaDuelsRepo
from app.game.arena_duels import (
    service_baseline_complete,
    service_baseline_start,
    service_challenger_complete,
    service_common,
    service_listing,
)
from app.game.arena_duels.types import (
    ArenaActiveDuelSnapshot,
    ArenaAttemptCompletionResult,
    ArenaBaselineStartResult,
    ArenaDuelSnapshot,
)
from app.game.sessions.service.friend_challenges_question_plan import select_duel_question_ids
from app.game.sessions.service.sessions_start import start_session


async def create_arena_duel_baseline(
    session: AsyncSession,
    *,
    creator_user_id: int,
    mode_code: str,
    now_utc: datetime,
    access_type: str,
) -> ArenaBaselineStartResult:
    _sync_dependencies()
    return await service_baseline_start.create_arena_duel_baseline(
        session,
        creator_user_id=creator_user_id,
        mode_code=mode_code,
        now_utc=now_utc,
        access_type=access_type,
    )


async def complete_arena_creator_baseline(
    session: AsyncSession,
    *,
    attempt_id: UUID,
    user_id: int,
    now_utc: datetime,
) -> ArenaDuelSnapshot:
    _sync_dependencies()
    return await service_baseline_complete.complete_arena_creator_baseline(
        session,
        attempt_id=attempt_id,
        user_id=user_id,
        now_utc=now_utc,
    )


async def complete_arena_creator_baseline_if_applicable(
    session: AsyncSession,
    *,
    attempt_id: UUID,
    user_id: int,
    now_utc: datetime,
) -> ArenaDuelSnapshot | None:
    _sync_dependencies()
    return await service_baseline_complete.complete_arena_creator_baseline_if_applicable(
        session,
        attempt_id=attempt_id,
        user_id=user_id,
        now_utc=now_utc,
    )


async def complete_arena_attempt_if_applicable(
    session: AsyncSession,
    *,
    attempt_id: UUID,
    user_id: int,
    now_utc: datetime,
) -> ArenaAttemptCompletionResult | None:
    _sync_dependencies()
    return await service_challenger_complete.complete_arena_attempt_if_applicable(
        session,
        attempt_id=attempt_id,
        user_id=user_id,
        now_utc=now_utc,
    )


async def list_active_arena_duels(
    session: AsyncSession,
    *,
    now_utc: datetime,
    limit: int = 10,
) -> tuple[ArenaActiveDuelSnapshot, ...]:
    _sync_dependencies()
    return await service_listing.list_active_arena_duels(
        session,
        now_utc=now_utc,
        limit=limit,
    )


def _sync_dependencies() -> None:
    service_common.ArenaDuelsRepo = ArenaDuelsRepo  # type: ignore[misc]
    service_listing.ArenaDuelsRepo = ArenaDuelsRepo  # type: ignore[misc]
    service_baseline_start.ArenaDuelsRepo = ArenaDuelsRepo  # type: ignore[misc]
    service_baseline_start.select_duel_question_ids = select_duel_question_ids
    service_baseline_start.start_session = start_session
    service_baseline_complete.ArenaDuelsRepo = ArenaDuelsRepo  # type: ignore[misc]
    service_challenger_complete.ArenaDuelsRepo = ArenaDuelsRepo  # type: ignore[misc]
