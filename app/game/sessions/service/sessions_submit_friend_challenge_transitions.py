from __future__ import annotations

from datetime import datetime

from app.game.friend_challenges.constants import (
    DUEL_STATUS_ACCEPTED,
    DUEL_STATUS_COMPLETED,
    DUEL_STATUS_CREATOR_DONE,
    DUEL_STATUS_OPPONENT_DONE,
    DUEL_STATUS_PENDING,
    is_duel_playable_for_user,
    is_duel_playable_status,
)

from .sessions_submit_friend_challenge_state import _FriendChallengeAnswerState


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


def apply_playable_friend_challenge_answer(
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


def is_waiting_for_opponent(state: _FriendChallengeAnswerState) -> bool:
    if not _is_playable_for_participant(state):
        return False
    if not state.has_opponent:
        return True

    challenge = state.challenge
    opponent_answered_round = (
        challenge.opponent_answered_round if state.is_creator else challenge.creator_answered_round
    )
    return opponent_answered_round < state.answered_round
