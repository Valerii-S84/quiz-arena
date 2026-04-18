from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.friend_challenges.constants import (
    DUEL_STATUS_ACCEPTED,
    DUEL_STATUS_COMPLETED,
    DUEL_STATUS_CREATOR_DONE,
    DUEL_STATUS_OPPONENT_DONE,
    DUEL_STATUS_PENDING,
    is_duel_playable_for_user,
    is_duel_playable_status,
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


@dataclass(slots=True)
class _FriendChallengeAnswerState:
    challenge: FriendChallenge
    answered_round: int
    has_opponent: bool
    is_creator: bool


async def _load_friend_challenge_answer_state(
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


def _is_playable_for_participant(state: _FriendChallengeAnswerState) -> bool:
    return is_duel_playable_for_user(
        status=state.challenge.status,
        has_opponent=state.has_opponent,
        is_creator=state.is_creator,
    )


def _record_participant_answer(
    state: _FriendChallengeAnswerState,
    *,
    is_correct: bool,
) -> None:
    challenge = state.challenge
    if state.is_creator:
        if challenge.creator_answered_round >= state.answered_round:
            return
        if is_correct:
            challenge.creator_score += 1
        challenge.creator_answered_round = state.answered_round
        return

    if challenge.opponent_answered_round >= state.answered_round:
        return
    if is_correct:
        challenge.opponent_score += 1
    challenge.opponent_answered_round = state.answered_round


def _is_round_completed(state: _FriendChallengeAnswerState) -> bool:
    challenge = state.challenge
    return (
        state.has_opponent
        and challenge.creator_answered_round >= state.answered_round
        and challenge.opponent_answered_round >= state.answered_round
        and is_duel_playable_status(challenge.status)
    )


def _mark_participants_finished(
    state: _FriendChallengeAnswerState,
    *,
    now_utc: datetime,
) -> None:
    challenge = state.challenge
    if challenge.creator_answered_round >= challenge.total_rounds:
        challenge.creator_finished_at = challenge.creator_finished_at or now_utc
    if challenge.opponent_answered_round >= challenge.total_rounds:
        challenge.opponent_finished_at = challenge.opponent_finished_at or now_utc


def _mark_duel_completed(
    state: _FriendChallengeAnswerState,
    *,
    now_utc: datetime,
) -> None:
    challenge = state.challenge
    challenge.current_round = challenge.total_rounds
    challenge.status = DUEL_STATUS_COMPLETED
    challenge.completed_at = now_utc
    if challenge.creator_score > challenge.opponent_score:
        challenge.winner_user_id = challenge.creator_user_id
    elif (
        challenge.opponent_score > challenge.creator_score
        and challenge.opponent_user_id is not None
    ):
        challenge.winner_user_id = challenge.opponent_user_id
    else:
        challenge.winner_user_id = None


def _resolve_in_progress_status(state: _FriendChallengeAnswerState) -> str:
    challenge = state.challenge
    if challenge.creator_finished_at:
        return DUEL_STATUS_CREATOR_DONE
    if challenge.opponent_finished_at:
        return DUEL_STATUS_OPPONENT_DONE
    return DUEL_STATUS_ACCEPTED if state.has_opponent else DUEL_STATUS_PENDING


def _apply_playable_friend_challenge_answer(
    state: _FriendChallengeAnswerState,
    *,
    is_correct: bool,
    now_utc: datetime,
) -> bool:
    if not _is_playable_for_participant(state):
        return False

    challenge = state.challenge
    _record_participant_answer(state, is_correct=is_correct)
    friend_round_completed = _is_round_completed(state)
    challenge.current_round = min(
        challenge.total_rounds,
        max(challenge.creator_answered_round, challenge.opponent_answered_round) + 1,
    )
    _mark_participants_finished(state, now_utc=now_utc)
    if challenge.creator_finished_at and challenge.opponent_finished_at:
        _mark_duel_completed(state, now_utc=now_utc)
        return True

    challenge.status = _resolve_in_progress_status(state)
    return friend_round_completed


def _is_waiting_for_opponent(state: _FriendChallengeAnswerState) -> bool:
    if not _is_playable_for_participant(state):
        return False
    if not state.has_opponent:
        return True

    challenge = state.challenge
    opponent_answered_round = (
        challenge.opponent_answered_round if state.is_creator else challenge.creator_answered_round
    )
    return opponent_answered_round < state.answered_round


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
    answer_state = await _load_friend_challenge_answer_state(
        session,
        quiz_session=quiz_session,
        user_id=user_id,
        now_utc=now_utc,
    )
    if answer_state is None:
        return None, False, False

    friend_round_completed = _apply_playable_friend_challenge_answer(
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
    friend_waiting_for_opponent = _is_waiting_for_opponent(answer_state)
    await _emit_completed_duel_event_if_needed(
        session,
        challenge=challenge,
        user_id=user_id,
        now_utc=now_utc,
    )
    return friend_snapshot, friend_round_completed, friend_waiting_for_opponent
