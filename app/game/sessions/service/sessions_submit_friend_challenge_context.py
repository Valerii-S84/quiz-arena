from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.friend_challenges.constants import normalize_duel_status
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError

from .friend_challenges_expiry import (
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
)
from .sessions_submit_friend_challenge_state import _FriendChallengeAnswerState


async def load_friend_challenge_answer_state(
    session: AsyncSession,
    *,
    quiz_session: QuizSession,
    user_id: int,
    now_utc: datetime,
) -> _FriendChallengeAnswerState | None:
    if quiz_session.source != "FRIEND_CHALLENGE" or quiz_session.friend_challenge_id is None:
        return None

    challenge = await FriendChallengesRepo.get_by_id_for_update(
        session,
        quiz_session.friend_challenge_id,
    )
    if challenge is None:
        raise FriendChallengeNotFoundError

    has_opponent = challenge.opponent_user_id is not None
    challenge.status = normalize_duel_status(
        status=challenge.status,
        has_opponent=has_opponent,
    )
    is_creator = challenge.creator_user_id == user_id
    if not is_creator and challenge.opponent_user_id != user_id:
        raise FriendChallengeAccessError

    if _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
        await _emit_friend_challenge_expired_event(
            session,
            challenge=challenge,
            happened_at=now_utc,
            source=EVENT_SOURCE_BOT,
        )

    return _FriendChallengeAnswerState(
        challenge=challenge,
        answered_round=quiz_session.friend_challenge_round or 1,
        has_opponent=has_opponent,
        is_creator=is_creator,
    )
