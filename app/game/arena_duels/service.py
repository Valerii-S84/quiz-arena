from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.db.repo.arena_duels_repo import ArenaDuelsRepo
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.arena_duels import (
    service_baseline_complete,
    service_baseline_start,
    service_challenger_complete,
    service_common,
    service_listing,
)
from app.game.arena_duels.constants import ARENA_DUEL_STATUS_ACTIVE
from app.game.arena_duels.types import (
    ArenaActiveDuelSnapshot,
    ArenaAttemptCompletionResult,
    ArenaBaselineStartResult,
    ArenaDuelSnapshot,
)
from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.friend_challenges.constants import DUEL_TYPE_DIRECT
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeLimitExceededError
from app.game.sessions.service.constants import DUEL_MAX_ACTIVE_PER_USER, DUEL_MAX_NEW_PER_DAY
from app.game.sessions.service.friend_challenges_analytics import emit_standard_duel_created_events
from app.game.sessions.service.friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _create_friend_challenge_row,
    _resolve_friend_challenge_access_type,
)
from app.game.sessions.service.friend_challenges_question_plan import (
    berlin_day_start_utc,
    select_duel_question_ids,
)
from app.game.sessions.service.sessions_start import start_session
from app.game.sessions.types import FriendChallengeSnapshot


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


async def create_friend_challenge_from_arena_duel(
    session: AsyncSession,
    *,
    creator_user_id: int,
    arena_duel_id: UUID,
    now_utc: datetime,
) -> FriendChallengeSnapshot:
    duel = await ArenaDuelsRepo.get_duel_for_update(session, duel_id=arena_duel_id)
    if duel is None or duel.creator_user_id != creator_user_id:
        raise FriendChallengeAccessError
    question_ids = tuple(duel.question_ids or ())
    if duel.status != ARENA_DUEL_STATUS_ACTIVE or len(question_ids) != DUEL_QUESTION_COUNT:
        raise FriendChallengeAccessError

    live_duel_count = await FriendChallengesRepo.count_live_for_user(
        session,
        user_id=creator_user_id,
    )
    if live_duel_count >= DUEL_MAX_ACTIVE_PER_USER:
        raise FriendChallengeLimitExceededError
    created_today = await FriendChallengesRepo.count_created_since(
        session,
        creator_user_id=creator_user_id,
        created_after_utc=berlin_day_start_utc(now_utc=now_utc),
    )
    if created_today >= DUEL_MAX_NEW_PER_DAY:
        raise FriendChallengeLimitExceededError

    access_type = await _resolve_friend_challenge_access_type(
        session,
        creator_user_id=creator_user_id,
        now_utc=now_utc,
    )
    challenge_id = uuid4()
    challenge = await _create_friend_challenge_row(
        session,
        challenge_id=challenge_id,
        creator_user_id=creator_user_id,
        opponent_user_id=None,
        challenge_type=DUEL_TYPE_DIRECT,
        mode_code=duel.mode_code,
        access_type=access_type,
        total_rounds=DUEL_QUESTION_COUNT,
        now_utc=now_utc,
        question_ids=list(question_ids),
    )
    await emit_standard_duel_created_events(
        session,
        challenge=challenge,
        happened_at=now_utc,
        source=EVENT_SOURCE_BOT,
        creator_user_id=creator_user_id,
        entrypoint="arena_friend",
        arena_duel_id=arena_duel_id,
    )
    return _build_friend_challenge_snapshot(challenge)


def _sync_dependencies() -> None:
    service_common.ArenaDuelsRepo = ArenaDuelsRepo  # type: ignore[misc]
    service_listing.ArenaDuelsRepo = ArenaDuelsRepo  # type: ignore[misc]
    service_baseline_start.ArenaDuelsRepo = ArenaDuelsRepo  # type: ignore[misc]
    service_baseline_start.select_duel_question_ids = select_duel_question_ids
    service_baseline_start.start_session = start_session
    service_baseline_complete.ArenaDuelsRepo = ArenaDuelsRepo  # type: ignore[misc]
    service_challenger_complete.ArenaDuelsRepo = ArenaDuelsRepo  # type: ignore[misc]
