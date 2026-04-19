from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge
from app.db.models.quiz_sessions import QuizSession
from app.game.friend_challenges.constants import DUEL_STATUS_COMPLETED
from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_internal import _build_friend_challenge_snapshot
from .friend_challenges_tournament_progress import handle_tournament_duel_progress
from .sessions_submit_friend_challenge_context import load_friend_challenge_answer_state
from .sessions_submit_friend_challenge_transitions import (
    apply_playable_friend_challenge_answer,
    is_waiting_for_opponent,
)


def _build_duel_completed_payload(challenge: FriendChallenge) -> dict[str, object]:
    return {
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
    }


async def _emit_completed_duel_event_if_needed(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    user_id: int,
    now_utc: datetime,
) -> None:
    if challenge.status != DUEL_STATUS_COMPLETED or challenge.completed_at != now_utc:
        return

    await emit_analytics_event(
        session,
        event_type="duel_completed",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=user_id,
        payload=_build_duel_completed_payload(challenge),
    )


async def _apply_friend_challenge_answer(
    session: AsyncSession,
    *,
    quiz_session: QuizSession,
    user_id: int,
    is_correct: bool,
    now_utc: datetime,
) -> tuple[FriendChallengeSnapshot | None, bool, bool]:
    answer_state = await load_friend_challenge_answer_state(
        session,
        quiz_session=quiz_session,
        user_id=user_id,
        now_utc=now_utc,
    )
    if answer_state is None:
        return None, False, False

    friend_round_completed = apply_playable_friend_challenge_answer(
        answer_state,
        is_correct=is_correct,
        now_utc=now_utc,
    )
    challenge = answer_state.challenge
    challenge.updated_at = now_utc
    if challenge.tournament_match_id is not None:
        await handle_tournament_duel_progress(
            session,
            challenge=challenge,
            user_id=user_id,
            now_utc=now_utc,
        )

    friend_snapshot = _build_friend_challenge_snapshot(challenge)
    friend_waiting_for_opponent = is_waiting_for_opponent(answer_state)
    await _emit_completed_duel_event_if_needed(
        session,
        challenge=challenge,
        user_id=user_id,
        now_utc=now_utc,
    )
    return friend_snapshot, friend_round_completed, friend_waiting_for_opponent
