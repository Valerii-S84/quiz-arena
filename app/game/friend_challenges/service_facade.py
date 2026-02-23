from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.sessions.service import GameSessionService
from app.game.friend_challenges.ui_contract import (
    FRIEND_CHALLENGE_LEVEL_SEQUENCE as _FRIEND_CHALLENGE_LEVEL_SEQUENCE,
)
from app.game.sessions.types import FriendChallengeRoundStartResult, FriendChallengeSnapshot

FRIEND_CHALLENGE_LEVEL_SEQUENCE = _FRIEND_CHALLENGE_LEVEL_SEQUENCE


class FriendChallengeServiceFacade:
    """Facade for friend challenge operations used by bot orchestration."""

    @staticmethod
    async def create_challenge(
        session: AsyncSession,
        *,
        creator_user_id: int,
        mode_code: str,
        now_utc: datetime,
        total_rounds: int,
    ) -> FriendChallengeSnapshot:
        return await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code=mode_code,
            now_utc=now_utc,
            total_rounds=total_rounds,
        )

    @staticmethod
    async def create_rematch(
        session: AsyncSession,
        *,
        initiator_user_id: int,
        challenge_id: UUID,
        now_utc: datetime,
    ) -> FriendChallengeSnapshot:
        return await GameSessionService.create_friend_challenge_rematch(
            session,
            initiator_user_id=initiator_user_id,
            challenge_id=challenge_id,
            now_utc=now_utc,
        )

    @staticmethod
    async def create_best_of_three(
        session: AsyncSession,
        *,
        initiator_user_id: int,
        challenge_id: UUID,
        now_utc: datetime,
    ) -> FriendChallengeSnapshot:
        return await GameSessionService.create_friend_challenge_best_of_three(
            session,
            initiator_user_id=initiator_user_id,
            challenge_id=challenge_id,
            now_utc=now_utc,
            best_of=3,
        )

    @staticmethod
    async def create_series_next_game(
        session: AsyncSession,
        *,
        initiator_user_id: int,
        challenge_id: UUID,
        now_utc: datetime,
    ) -> FriendChallengeSnapshot:
        return await GameSessionService.create_friend_challenge_series_next_game(
            session,
            initiator_user_id=initiator_user_id,
            challenge_id=challenge_id,
            now_utc=now_utc,
        )

    @staticmethod
    async def start_round(
        session: AsyncSession,
        *,
        user_id: int,
        challenge_id: UUID,
        idempotency_key: str,
        now_utc: datetime,
    ) -> FriendChallengeRoundStartResult:
        return await GameSessionService.start_friend_challenge_round(
            session,
            user_id=user_id,
            challenge_id=challenge_id,
            idempotency_key=idempotency_key,
            now_utc=now_utc,
        )

    @staticmethod
    async def get_snapshot_for_user(
        session: AsyncSession,
        *,
        user_id: int,
        challenge_id: UUID,
        now_utc: datetime,
    ) -> FriendChallengeSnapshot:
        return await GameSessionService.get_friend_challenge_snapshot_for_user(
            session,
            user_id=user_id,
            challenge_id=challenge_id,
            now_utc=now_utc,
        )

    @staticmethod
    async def get_series_score_for_user(
        session: AsyncSession,
        *,
        user_id: int,
        challenge_id: UUID,
        now_utc: datetime,
    ) -> tuple[int, int, int, int]:
        return await GameSessionService.get_friend_series_score_for_user(
            session,
            user_id=user_id,
            challenge_id=challenge_id,
            now_utc=now_utc,
        )
