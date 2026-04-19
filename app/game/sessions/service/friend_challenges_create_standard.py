from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.game.friend_challenges.constants import DUEL_TYPE_DIRECT
from app.game.sessions.types import FriendChallengeSnapshot

from .constants import FRIEND_CHALLENGE_TOTAL_ROUNDS
from .friend_challenges_create_analytics import emit_standard_duel_created_events
from .friend_challenges_create_drafts import build_create_friend_challenge_draft
from .friend_challenges_create_limits import resolve_friend_challenge_create_request
from .friend_challenges_create_rows import create_friend_challenge_from_draft
from .friend_challenges_records import _build_friend_challenge_snapshot


async def create_friend_challenge(
    session: AsyncSession,
    *,
    creator_user_id: int,
    mode_code: str,
    now_utc: datetime,
    challenge_type: str = DUEL_TYPE_DIRECT,
    total_rounds: int = FRIEND_CHALLENGE_TOTAL_ROUNDS,
) -> FriendChallengeSnapshot:
    request = await resolve_friend_challenge_create_request(
        session,
        creator_user_id=creator_user_id,
        challenge_type=challenge_type,
        total_rounds=total_rounds,
        now_utc=now_utc,
    )
    draft = await build_create_friend_challenge_draft(
        session,
        creator_user_id=creator_user_id,
        challenge_type=request.challenge_type,
        mode_code=mode_code,
        total_rounds=request.total_rounds,
        now_utc=now_utc,
    )
    challenge = await create_friend_challenge_from_draft(
        session,
        draft=draft,
        now_utc=now_utc,
    )
    await emit_standard_duel_created_events(
        session,
        challenge=challenge,
        happened_at=now_utc,
        source=EVENT_SOURCE_BOT,
        creator_user_id=creator_user_id,
    )
    return _build_friend_challenge_snapshot(challenge)
