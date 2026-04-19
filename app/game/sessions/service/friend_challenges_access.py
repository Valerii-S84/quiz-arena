from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.sessions.errors import FriendChallengePaymentRequiredError

from .constants import FRIEND_CHALLENGE_FREE_CREATES
from .friend_challenges_access_state import load_friend_challenge_access_state


async def _resolve_friend_challenge_access_type(
    session: AsyncSession,
    *,
    creator_user_id: int,
    now_utc: datetime,
) -> str:
    state = await load_friend_challenge_access_state(
        session,
        creator_user_id=creator_user_id,
        now_utc=now_utc,
    )
    if state.premium_active:
        return "PREMIUM"
    if state.free_count < FRIEND_CHALLENGE_FREE_CREATES:
        return "FREE"
    if state.paid_count >= state.paid_tickets:
        raise FriendChallengePaymentRequiredError
    return "PAID_TICKET"
