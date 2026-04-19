from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.users_repo import UsersRepo
from app.game.sessions.errors import FriendChallengeAccessError

from .constants import FRIEND_CHALLENGE_FREE_CREATES, FRIEND_CHALLENGE_TICKET_PRODUCT_CODE


@dataclass(slots=True)
class FriendChallengeAccessState:
    premium_active: bool
    free_count: int = 0
    paid_count: int = 0
    paid_tickets: int = 0


async def load_friend_challenge_access_state(
    session: AsyncSession,
    *,
    creator_user_id: int,
    now_utc: datetime,
) -> FriendChallengeAccessState:
    creator = await UsersRepo.get_by_id_for_update(session, creator_user_id)
    if creator is None:
        raise FriendChallengeAccessError

    premium_active = await EntitlementsRepo.has_active_premium(session, creator_user_id, now_utc)
    if premium_active:
        return FriendChallengeAccessState(premium_active=True)

    day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    free_count = await FriendChallengesRepo.count_by_creator_access_type(
        session,
        creator_user_id=creator_user_id,
        access_type="FREE",
        since=day_start,
    )
    if free_count < FRIEND_CHALLENGE_FREE_CREATES:
        return FriendChallengeAccessState(
            premium_active=False,
            free_count=free_count,
        )

    paid_count = await FriendChallengesRepo.count_by_creator_access_type(
        session,
        creator_user_id=creator_user_id,
        access_type="PAID_TICKET",
    )
    paid_tickets = await PurchasesRepo.count_credited_product(
        session,
        user_id=creator_user_id,
        product_code=FRIEND_CHALLENGE_TICKET_PRODUCT_CODE,
    )
    return FriendChallengeAccessState(
        premium_active=False,
        free_count=free_count,
        paid_count=paid_count,
        paid_tickets=paid_tickets,
    )
