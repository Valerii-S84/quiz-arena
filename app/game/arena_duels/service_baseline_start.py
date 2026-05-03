from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.repo.arena_duels_repo import ArenaDuelsRepo
from app.game.arena_duels.analytics import (
    ARENA_EVENT_ARENA_DUEL_CREATED,
    ARENA_EVENT_ARENA_DUEL_STARTED,
    build_arena_event_payload,
    emit_arena_analytics_event,
)
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_DRAFT,
    ARENA_SOURCE,
    arena_duel_expires_at,
)
from app.game.arena_duels.service_common import build_duel_snapshot, validate_question_ids
from app.game.arena_duels.types import ArenaBaselineStartResult
from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.duels.limits import DuelLimitService
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
    DuelLimitService.assert_resolved_access_type(ARENA_SOURCE, access_type=access_type)
    duel_id = uuid4()
    question_ids = await select_duel_question_ids(
        session,
        mode_code=mode_code,
        total_rounds=DUEL_QUESTION_COUNT,
        now_utc=now_utc,
        challenge_seed=str(duel_id),
    )
    duel = await _create_duel(
        session,
        duel_id=duel_id,
        creator_user_id=creator_user_id,
        mode_code=mode_code,
        access_type=access_type,
        question_ids=question_ids,
        now_utc=now_utc,
    )
    baseline_attempt = await _create_baseline_attempt(
        session,
        duel=duel,
        creator_user_id=creator_user_id,
        access_type=access_type,
        now_utc=now_utc,
    )
    start_result = await start_session(
        session,
        user_id=creator_user_id,
        mode_code=mode_code,
        source=ARENA_SOURCE,
        idempotency_key=f"arena:baseline:{baseline_attempt.id}:1",
        now_utc=now_utc,
        arena_attempt_id=baseline_attempt.id,
        arena_round=1,
        duel_limit_checked=True,
    )
    await _emit_start_events(
        session,
        duel=duel,
        attempt=baseline_attempt,
        creator_user_id=creator_user_id,
        access_type=access_type,
        now_utc=now_utc,
    )
    return ArenaBaselineStartResult(
        duel=build_duel_snapshot(duel=duel, baseline_attempt=None),
        baseline_attempt_id=baseline_attempt.id,
        start_result=start_result,
    )


async def _create_duel(
    session: AsyncSession,
    *,
    duel_id,
    creator_user_id: int,
    mode_code: str,
    access_type: str,
    question_ids,
    now_utc: datetime,
) -> ArenaDuel:
    return await ArenaDuelsRepo.create_duel(
        session,
        duel=ArenaDuel(
            id=duel_id,
            creator_user_id=creator_user_id,
            baseline_attempt_id=None,
            question_ids=list(validate_question_ids(question_ids)),
            mode_code=mode_code,
            access_type=access_type,
            status=ARENA_DUEL_STATUS_DRAFT,
            expires_at=arena_duel_expires_at(now_utc=now_utc),
            created_at=now_utc,
            updated_at=now_utc,
            source_friend_challenge_id=None,
        ),
    )


async def _create_baseline_attempt(
    session: AsyncSession,
    *,
    duel: ArenaDuel,
    creator_user_id: int,
    access_type: str,
    now_utc: datetime,
) -> ArenaAttempt:
    return await ArenaDuelsRepo.create_attempt(
        session,
        attempt=ArenaAttempt(
            id=uuid4(),
            arena_duel_id=duel.id,
            user_id=creator_user_id,
            role=ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
            access_type=access_type,
            score=None,
            time_ms=None,
            result=None,
            completed_at=None,
            created_at=now_utc,
        ),
    )


async def _emit_start_events(
    session: AsyncSession,
    *,
    duel: ArenaDuel,
    attempt: ArenaAttempt,
    creator_user_id: int,
    access_type: str,
    now_utc: datetime,
) -> None:
    for event_type in (ARENA_EVENT_ARENA_DUEL_CREATED, ARENA_EVENT_ARENA_DUEL_STARTED):
        await emit_arena_analytics_event(
            session,
            event_type=event_type,
            happened_at=now_utc,
            user_id=creator_user_id,
            payload=build_arena_event_payload(
                user_id=creator_user_id,
                arena_duel_id=duel.id,
                attempt_id=attempt.id,
                action="create",
                access_type=access_type,
            ),
        )
