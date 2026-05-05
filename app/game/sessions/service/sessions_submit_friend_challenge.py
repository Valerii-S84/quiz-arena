from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.game.arena_duels.analytics import ARENA_EVENT_FRIEND_DUEL_COMPLETED
from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.friend_challenges.constants import (
    DUEL_STATUS_ACCEPTED,
    DUEL_STATUS_COMPLETED,
    DUEL_STATUS_CREATOR_DONE,
    DUEL_STATUS_OPPONENT_DONE,
    DUEL_STATUS_PENDING,
    DUEL_TYPE_DIRECT,
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


@dataclass(frozen=True, slots=True)
class _FriendDuelTiming:
    creator_time_ms: int
    opponent_time_ms: int


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
    friend_result_timing: _FriendDuelTiming | None = None
    if quiz_session.source == "FRIEND_CHALLENGE" and quiz_session.friend_challenge_id is not None:
        challenge = await FriendChallengesRepo.get_by_id_for_update(
            session,
            quiz_session.friend_challenge_id,
        )
        if challenge is None:
            raise FriendChallengeNotFoundError
        challenge.status = normalize_duel_status(
            status=challenge.status,
            has_opponent=challenge.opponent_user_id is not None,
        )

        is_creator = challenge.creator_user_id == user_id
        has_opponent = challenge.opponent_user_id is not None
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

        if is_duel_playable_for_user(
            status=challenge.status,
            has_opponent=has_opponent,
            is_creator=is_creator,
        ):
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
                has_opponent
                and challenge.creator_answered_round >= answered_round
                and challenge.opponent_answered_round >= answered_round
            )
            if both_answered_round and is_duel_playable_status(challenge.status):
                friend_round_completed = True

            max_answered_round = max(
                challenge.creator_answered_round,
                challenge.opponent_answered_round,
            )
            challenge.current_round = min(challenge.total_rounds, max_answered_round + 1)

            if challenge.creator_answered_round >= challenge.total_rounds:
                challenge.creator_finished_at = challenge.creator_finished_at or now_utc
            if challenge.opponent_answered_round >= challenge.total_rounds:
                challenge.opponent_finished_at = challenge.opponent_finished_at or now_utc

            if challenge.creator_finished_at and challenge.opponent_finished_at:
                friend_round_completed = True
                challenge.current_round = challenge.total_rounds
                challenge.status = DUEL_STATUS_COMPLETED
                challenge.completed_at = now_utc
                friend_result_timing = await _resolve_friend_duel_timing_if_needed(
                    session,
                    challenge=challenge,
                )
                challenge.winner_user_id = _resolve_friend_challenge_winner(
                    challenge,
                    timing=friend_result_timing,
                )
            elif challenge.creator_finished_at:
                challenge.status = DUEL_STATUS_CREATOR_DONE
            elif challenge.opponent_finished_at:
                challenge.status = DUEL_STATUS_OPPONENT_DONE
            else:
                challenge.status = DUEL_STATUS_ACCEPTED if has_opponent else DUEL_STATUS_PENDING

        challenge.updated_at = now_utc
        if challenge.tournament_match_id is not None:
            await handle_tournament_duel_progress(
                session,
                challenge=challenge,
                user_id=user_id,
                now_utc=now_utc,
            )
        friend_snapshot = _build_friend_challenge_snapshot(challenge)
        if friend_result_timing is not None:
            friend_snapshot.creator_time_ms = friend_result_timing.creator_time_ms
            friend_snapshot.opponent_time_ms = friend_result_timing.opponent_time_ms
        friend_waiting_for_opponent = is_duel_playable_for_user(
            status=challenge.status,
            has_opponent=has_opponent,
            is_creator=is_creator,
        ) and (
            not has_opponent
            or (
                challenge.opponent_answered_round < answered_round
                if is_creator
                else challenge.creator_answered_round < answered_round
            )
        )
        if challenge.status == DUEL_STATUS_COMPLETED and challenge.completed_at == now_utc:
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
                    "series_id": (
                        str(challenge.series_id) if challenge.series_id is not None else None
                    ),
                    "series_game_number": challenge.series_game_number,
                    "series_best_of": challenge.series_best_of,
                },
            )
    return friend_snapshot, friend_round_completed, friend_waiting_for_opponent


def _resolve_friend_challenge_winner(
    challenge,
    *,
    timing: _FriendDuelTiming | None,
) -> int | None:
    if challenge.creator_score > challenge.opponent_score:
        return int(challenge.creator_user_id)
    if (
        challenge.opponent_score > challenge.creator_score
        and challenge.opponent_user_id is not None
    ):
        return int(challenge.opponent_user_id)
    if timing is None:
        return None
    return _resolve_time_tie_break_winner(challenge=challenge, timing=timing)


def _uses_time_tie_break(challenge) -> bool:
    return (
        challenge.tournament_match_id is None
        and challenge.challenge_type == DUEL_TYPE_DIRECT
        and int(challenge.total_rounds) == DUEL_QUESTION_COUNT
        and challenge.opponent_user_id is not None
    )


async def _resolve_friend_duel_timing_if_needed(
    session: AsyncSession,
    *,
    challenge,
) -> _FriendDuelTiming | None:
    if not _uses_time_tie_break(challenge):
        return None
    creator_time_ms = await QuizSessionsRepo.sum_completed_duration_ms_for_friend_challenge_user(
        session,
        friend_challenge_id=challenge.id,
        user_id=challenge.creator_user_id,
    )
    opponent_time_ms = await QuizSessionsRepo.sum_completed_duration_ms_for_friend_challenge_user(
        session,
        friend_challenge_id=challenge.id,
        user_id=challenge.opponent_user_id,
    )
    return _FriendDuelTiming(
        creator_time_ms=creator_time_ms,
        opponent_time_ms=opponent_time_ms,
    )


def _resolve_time_tie_break_winner(
    *,
    challenge,
    timing: _FriendDuelTiming,
) -> int | None:
    if timing.creator_time_ms < timing.opponent_time_ms:
        return int(challenge.creator_user_id)
    if timing.opponent_time_ms < timing.creator_time_ms:
        return int(challenge.opponent_user_id)
    return None
