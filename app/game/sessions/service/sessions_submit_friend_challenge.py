from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
)


async def _apply_friend_challenge_answer(
    session: AsyncSession,
    *,
    quiz_session: QuizSession,
    user_id: int,
    is_correct: bool,
    now_utc: datetime,
) -> tuple[FriendChallengeSnapshot | None, bool, bool]:
    friend_snapshot = None
    friend_round_completed = False
    friend_waiting_for_opponent = False
    if quiz_session.source == "FRIEND_CHALLENGE" and quiz_session.friend_challenge_id is not None:
        challenge = await FriendChallengesRepo.get_by_id_for_update(
            session,
            quiz_session.friend_challenge_id,
        )
        if challenge is None:
            raise FriendChallengeNotFoundError

        is_creator = challenge.creator_user_id == user_id
        if not is_creator and challenge.opponent_user_id != user_id:
            raise FriendChallengeAccessError

        answered_round = quiz_session.friend_challenge_round or 1
        expired_now = _expire_friend_challenge_if_due(
            challenge=challenge,
            now_utc=now_utc,
        )
        if expired_now:
            await _emit_friend_challenge_expired_event(
                session,
                challenge=challenge,
                happened_at=now_utc,
                source=EVENT_SOURCE_BOT,
            )

        if challenge.status == "ACTIVE":
            if is_creator:
                if challenge.creator_answered_round < answered_round:
                    if is_correct:
                        challenge.creator_score += 1
                    challenge.creator_answered_round = answered_round
            else:
                if challenge.opponent_answered_round < answered_round:
                    if is_correct:
                        challenge.opponent_score += 1
                    challenge.opponent_answered_round = answered_round

            both_answered_round = (
                challenge.opponent_user_id is not None
                and challenge.creator_answered_round >= answered_round
                and challenge.opponent_answered_round >= answered_round
            )
            if both_answered_round and challenge.status == "ACTIVE":
                friend_round_completed = True

            max_answered_round = max(
                challenge.creator_answered_round,
                challenge.opponent_answered_round,
            )
            challenge.current_round = min(challenge.total_rounds, max_answered_round + 1)

            if (
                challenge.status == "ACTIVE"
                and challenge.opponent_user_id is not None
                and challenge.creator_answered_round >= challenge.total_rounds
                and challenge.opponent_answered_round >= challenge.total_rounds
            ):
                friend_round_completed = True
                challenge.current_round = challenge.total_rounds
                challenge.status = "COMPLETED"
                challenge.completed_at = now_utc
                if challenge.creator_score > challenge.opponent_score:
                    challenge.winner_user_id = challenge.creator_user_id
                elif challenge.opponent_score > challenge.creator_score:
                    challenge.winner_user_id = challenge.opponent_user_id
                else:
                    challenge.winner_user_id = None

            if (
                challenge.status == "COMPLETED"
                and challenge.current_round >= challenge.total_rounds
            ):
                if challenge.creator_score > challenge.opponent_score:
                    challenge.winner_user_id = challenge.creator_user_id
                elif (
                    challenge.opponent_score > challenge.creator_score
                    and challenge.opponent_user_id is not None
                ):
                    challenge.winner_user_id = challenge.opponent_user_id
                else:
                    challenge.winner_user_id = None

        challenge.updated_at = now_utc
        friend_snapshot = _build_friend_challenge_snapshot(challenge)
        friend_waiting_for_opponent = challenge.status == "ACTIVE" and (
            challenge.opponent_user_id is None
            or (
                challenge.opponent_answered_round < answered_round
                if is_creator
                else challenge.creator_answered_round < answered_round
            )
        )
        if challenge.status == "COMPLETED" and challenge.completed_at == now_utc:
            await emit_analytics_event(
                session,
                event_type="friend_challenge_completed",
                source=EVENT_SOURCE_BOT,
                happened_at=now_utc,
                user_id=user_id,
                payload={
                    "challenge_id": str(challenge.id),
                    "creator_user_id": challenge.creator_user_id,
                    "opponent_user_id": challenge.opponent_user_id,
                    "creator_score": challenge.creator_score,
                    "opponent_score": challenge.opponent_score,
                    "winner_user_id": challenge.winner_user_id,
                    "total_rounds": challenge.total_rounds,
                    "expires_at": challenge.expires_at.isoformat(),
                    "series_id": (
                        str(challenge.series_id) if challenge.series_id is not None else None
                    ),
                    "series_game_number": challenge.series_game_number,
                    "series_best_of": challenge.series_best_of,
                },
            )
    return friend_snapshot, friend_round_completed, friend_waiting_for_opponent
