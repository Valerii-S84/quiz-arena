from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.users_repo import UsersRepo
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengePaymentRequiredError
from app.game.sessions.types import FriendChallengeSnapshot

from .constants import (
    FRIEND_CHALLENGE_FREE_CREATES,
    FRIEND_CHALLENGE_TICKET_PRODUCT_CODE,
    FRIEND_CHALLENGE_TTL_SECONDS,
)


def _friend_challenge_expires_at(*, now_utc: datetime) -> datetime:
    return now_utc + timedelta(seconds=FRIEND_CHALLENGE_TTL_SECONDS)


def _expire_friend_challenge_if_due(*, challenge: FriendChallenge, now_utc: datetime) -> bool:
    if challenge.status != "ACTIVE":
        return False
    if challenge.expires_at > now_utc:
        return False
    challenge.status = "EXPIRED"
    challenge.winner_user_id = None
    challenge.completed_at = now_utc
    challenge.updated_at = now_utc
    return True


async def _emit_friend_challenge_expired_event(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    happened_at: datetime,
    source: str,
) -> None:
    await emit_analytics_event(
        session,
        event_type="friend_challenge_expired",
        source=source,
        happened_at=happened_at,
        user_id=None,
        payload={
            "challenge_id": str(challenge.id),
            "creator_user_id": challenge.creator_user_id,
            "opponent_user_id": challenge.opponent_user_id,
            "creator_score": challenge.creator_score,
            "opponent_score": challenge.opponent_score,
            "total_rounds": challenge.total_rounds,
            "expires_at": challenge.expires_at.isoformat(),
        },
    )


async def _resolve_friend_challenge_access_type(
    session: AsyncSession,
    *,
    creator_user_id: int,
    now_utc: datetime,
) -> str:
    creator = await UsersRepo.get_by_id_for_update(session, creator_user_id)
    if creator is None:
        raise FriendChallengeAccessError

    premium_active = await EntitlementsRepo.has_active_premium(session, creator_user_id, now_utc)
    access_type = "PREMIUM"
    if not premium_active:
        free_count = await FriendChallengesRepo.count_by_creator_access_type(
            session,
            creator_user_id=creator_user_id,
            access_type="FREE",
        )
        if free_count < FRIEND_CHALLENGE_FREE_CREATES:
            access_type = "FREE"
        else:
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
            if paid_count >= paid_tickets:
                raise FriendChallengePaymentRequiredError
            access_type = "PAID_TICKET"
    return access_type


async def _create_friend_challenge_row(
    session: AsyncSession,
    *,
    creator_user_id: int,
    opponent_user_id: int | None,
    mode_code: str,
    access_type: str,
    total_rounds: int,
    now_utc: datetime,
    series_id: UUID | None = None,
    series_game_number: int = 1,
    series_best_of: int = 1,
) -> FriendChallenge:
    challenge = await FriendChallengesRepo.create(
        session,
        challenge=FriendChallenge(
            id=uuid4(),
            invite_token=uuid4().hex,
            creator_user_id=creator_user_id,
            opponent_user_id=opponent_user_id,
            mode_code=mode_code,
            access_type=access_type,
            status="ACTIVE",
            current_round=1,
            total_rounds=max(1, total_rounds),
            series_id=series_id,
            series_game_number=max(1, int(series_game_number)),
            series_best_of=max(1, int(series_best_of)),
            creator_score=0,
            opponent_score=0,
            creator_answered_round=0,
            opponent_answered_round=0,
            winner_user_id=None,
            expires_at=_friend_challenge_expires_at(now_utc=now_utc),
            expires_last_chance_notified_at=None,
            created_at=now_utc,
            updated_at=now_utc,
            completed_at=None,
        ),
    )
    return challenge


def _build_friend_challenge_snapshot(challenge: FriendChallenge) -> FriendChallengeSnapshot:
    return FriendChallengeSnapshot(
        challenge_id=challenge.id,
        invite_token=challenge.invite_token,
        mode_code=challenge.mode_code,
        access_type=challenge.access_type,
        status=challenge.status,
        creator_user_id=challenge.creator_user_id,
        opponent_user_id=challenge.opponent_user_id,
        current_round=challenge.current_round,
        total_rounds=challenge.total_rounds,
        series_id=challenge.series_id,
        series_game_number=challenge.series_game_number,
        series_best_of=challenge.series_best_of,
        creator_score=challenge.creator_score,
        opponent_score=challenge.opponent_score,
        winner_user_id=challenge.winner_user_id,
        expires_at=challenge.expires_at,
    )


def _series_wins_needed(*, best_of: int) -> int:
    resolved_best_of = max(1, int(best_of))
    return (resolved_best_of // 2) + 1


def _count_series_wins(
    *,
    series_challenges: list[FriendChallenge],
    creator_user_id: int,
    opponent_user_id: int | None,
) -> tuple[int, int]:
    creator_wins = 0
    opponent_wins = 0
    for item in series_challenges:
        if item.status not in {"COMPLETED", "EXPIRED"}:
            continue
        if item.winner_user_id == creator_user_id:
            creator_wins += 1
        elif opponent_user_id is not None and item.winner_user_id == opponent_user_id:
            opponent_wins += 1
    return creator_wins, opponent_wins


def _resolve_challenge_opponent_user_id(
    *,
    challenge: FriendChallenge,
    initiator_user_id: int,
) -> int:
    if challenge.creator_user_id == initiator_user_id:
        opponent_user_id = challenge.opponent_user_id
    else:
        opponent_user_id = challenge.creator_user_id
    if opponent_user_id is None:
        raise FriendChallengeAccessError
    return opponent_user_id
