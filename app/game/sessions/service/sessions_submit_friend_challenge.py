from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.arena_duels.analytics import ARENA_EVENT_FRIEND_DUEL_COMPLETED
from app.game.friend_challenges.constants import (
    DUEL_STATUS_COMPLETED,
    is_duel_playable_for_user,
    normalize_duel_status,
)
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
)
from .friend_challenges_tournament_progress import handle_tournament_duel_progress
from .sessions_submit_friend_challenge_progress import record_friend_challenge_answer
from .sessions_submit_friend_challenge_resolution import FriendDuelTiming


async def _apply_friend_challenge_answer(
    session: AsyncSession,
    *,
    quiz_session: QuizSession,
    user_id: int,
    is_correct: bool,
    now_utc: datetime,
) -> tuple[FriendChallengeSnapshot | None, bool, bool]:
    if quiz_session.source != "FRIEND_CHALLENGE" or quiz_session.friend_challenge_id is None:
        return None, False, False

    challenge = await _load_answerable_friend_challenge(
        session,
        challenge_id=quiz_session.friend_challenge_id,
    )
    is_creator = challenge.creator_user_id == user_id
    has_opponent = challenge.opponent_user_id is not None
    if not is_creator and challenge.opponent_user_id != user_id:
        raise FriendChallengeAccessError

    answered_round = quiz_session.friend_challenge_round or 1
    await _expire_friend_challenge_for_answer(
        session,
        challenge=challenge,
        now_utc=now_utc,
    )
    round_completed, result_timing = await record_friend_challenge_answer(
        session,
        challenge=challenge,
        is_creator=is_creator,
        has_opponent=has_opponent,
        answered_round=answered_round,
        is_correct=is_correct,
        now_utc=now_utc,
    )

    challenge.updated_at = now_utc
    if challenge.tournament_match_id is not None:
        await handle_tournament_duel_progress(
            session,
            challenge=challenge,
            user_id=user_id,
            now_utc=now_utc,
        )

    friend_snapshot = _build_snapshot_with_timing(challenge, timing=result_timing)
    waiting_for_opponent = _is_waiting_for_opponent(
        challenge,
        is_creator=is_creator,
        has_opponent=has_opponent,
        answered_round=answered_round,
    )
    if _completed_on_this_answer(challenge, now_utc=now_utc):
        await _emit_friend_duel_completed_event(
            session,
            challenge=challenge,
            user_id=user_id,
            now_utc=now_utc,
        )
    return friend_snapshot, round_completed, waiting_for_opponent


async def _load_answerable_friend_challenge(
    session: AsyncSession,
    *,
    challenge_id: UUID,
) -> FriendChallenge:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    if challenge is None:
        raise FriendChallengeNotFoundError
    challenge.status = normalize_duel_status(
        status=challenge.status,
        has_opponent=challenge.opponent_user_id is not None,
    )
    return challenge


async def _expire_friend_challenge_for_answer(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    now_utc: datetime,
) -> None:
    expired_now = _expire_friend_challenge_if_due(
        challenge=challenge,
        now_utc=now_utc,
    )
    if not expired_now:
        return
    await _emit_friend_challenge_expired_event(
        session,
        challenge=challenge,
        happened_at=now_utc,
        source=EVENT_SOURCE_BOT,
    )


def _build_snapshot_with_timing(
    challenge: FriendChallenge,
    *,
    timing: FriendDuelTiming | None,
) -> FriendChallengeSnapshot:
    friend_snapshot = _build_friend_challenge_snapshot(challenge)
    if timing is not None:
        friend_snapshot.creator_time_ms = timing.creator_time_ms
        friend_snapshot.opponent_time_ms = timing.opponent_time_ms
    return friend_snapshot


def _is_waiting_for_opponent(
    challenge: FriendChallenge,
    *,
    is_creator: bool,
    has_opponent: bool,
    answered_round: int,
) -> bool:
    playable = is_duel_playable_for_user(
        status=challenge.status,
        has_opponent=has_opponent,
        is_creator=is_creator,
    )
    if not playable:
        return False
    if not has_opponent:
        return True
    if is_creator:
        return challenge.opponent_answered_round < answered_round
    return challenge.creator_answered_round < answered_round


def _completed_on_this_answer(challenge: FriendChallenge, *, now_utc: datetime) -> bool:
    return challenge.status == DUEL_STATUS_COMPLETED and challenge.completed_at == now_utc


async def _emit_friend_duel_completed_event(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    user_id: int,
    now_utc: datetime,
) -> None:
    await emit_analytics_event(
        session,
        event_type=ARENA_EVENT_FRIEND_DUEL_COMPLETED,
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=user_id,
        payload={
            "challenge_id": str(challenge.id),
            "winner": challenge.winner_user_id,
            "creator_score": challenge.creator_score,
            "opponent_score": challenge.opponent_score,
            "creator_user_id": challenge.creator_user_id,
            "opponent_user_id": challenge.opponent_user_id,
            "winner_user_id": challenge.winner_user_id,
            "total_rounds": challenge.total_rounds,
            "expires_at": challenge.expires_at.isoformat(),
            "series_id": str(challenge.series_id) if challenge.series_id is not None else None,
            "series_game_number": challenge.series_game_number,
            "series_best_of": challenge.series_best_of,
        },
    )
