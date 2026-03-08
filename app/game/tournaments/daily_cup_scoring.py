from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournament_matches import TournamentMatch
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournament_round_scores_repo import (
    TournamentRoundScorePayload,
    TournamentRoundScoresRepo,
)

_AUTO_FINISH_PENALTY_TIME_MS = 2_147_483_647


@dataclass(frozen=True, slots=True)
class DailyCupPlayerResult:
    player_id: int
    opponent_id: int | None
    wins: int
    correct_answers: int
    total_time_ms: int
    is_draw: bool
    auto_finished: bool
    got_bye: bool


def _resolved_correct_answers(*, finished: bool, score: int) -> int:
    return max(0, int(score)) if finished else 0


def _auto_finish_time_ms(*, deadline: datetime) -> int:
    del deadline
    return _AUTO_FINISH_PENALTY_TIME_MS


def _points_for_result(*, score: int, opponent_score: int) -> int:
    if score > opponent_score:
        return 2
    if score == opponent_score:
        return 1
    return 0


async def build_daily_cup_player_results(
    session: AsyncSession,
    *,
    match: TournamentMatch,
    challenge,
    winner_id: int | None,
) -> tuple[DailyCupPlayerResult, DailyCupPlayerResult | None]:
    creator_user_id = int(challenge.creator_user_id)
    creator_done = bool(
        challenge.creator_finished_at is not None
        or int(challenge.creator_answered_round) >= int(challenge.total_rounds)
    )
    opponent_done = bool(
        challenge.opponent_finished_at is not None
        or int(challenge.opponent_answered_round) >= int(challenge.total_rounds)
    )
    creator_time_ms = (
        await QuizSessionsRepo.sum_completed_duration_ms_for_friend_challenge_user(
            session,
            friend_challenge_id=challenge.id,
            user_id=creator_user_id,
        )
        if creator_done
        else _auto_finish_time_ms(deadline=match.deadline)
    )
    opponent_user_id = int(challenge.opponent_user_id) if challenge.opponent_user_id is not None else None
    opponent_time_ms = (
        await QuizSessionsRepo.sum_completed_duration_ms_for_friend_challenge_user(
            session,
            friend_challenge_id=challenge.id,
            user_id=opponent_user_id,
        )
        if opponent_done and opponent_user_id is not None
        else _auto_finish_time_ms(deadline=match.deadline)
    )
    creator_score = _resolved_correct_answers(finished=creator_done, score=int(challenge.creator_score))
    if match.user_b is None:
        bot_score = int(challenge.opponent_score)
        return (
            DailyCupPlayerResult(
                player_id=creator_user_id,
                opponent_id=None,
                wins=0 if not creator_done else _points_for_result(score=creator_score, opponent_score=bot_score),
                correct_answers=creator_score,
                total_time_ms=creator_time_ms,
                is_draw=creator_done and creator_score == bot_score,
                auto_finished=not creator_done,
                got_bye=False,
            ),
            None,
        )
    creator_result = DailyCupPlayerResult(
        player_id=creator_user_id,
        opponent_id=opponent_user_id,
        wins=0 if not creator_done else _points_for_result(score=creator_score, opponent_score=int(challenge.opponent_score)),
        correct_answers=creator_score,
        total_time_ms=creator_time_ms,
        is_draw=winner_id is None,
        auto_finished=not creator_done,
        got_bye=False,
    )
    if opponent_user_id is None:
        return creator_result, None
    opponent_score = _resolved_correct_answers(
        finished=opponent_done, score=int(challenge.opponent_score)
    )
    opponent_result = DailyCupPlayerResult(
        player_id=opponent_user_id,
        opponent_id=creator_user_id,
        wins=0 if not opponent_done else _points_for_result(score=opponent_score, opponent_score=int(challenge.creator_score)),
        correct_answers=opponent_score,
        total_time_ms=opponent_time_ms,
        is_draw=winner_id is None,
        auto_finished=not opponent_done,
        got_bye=False,
    )
    return creator_result, opponent_result


async def store_daily_cup_player_result(
    session: AsyncSession,
    *,
    match: TournamentMatch,
    result: DailyCupPlayerResult,
    created_at: datetime,
) -> None:
    await TournamentParticipantsRepo.apply_score_delta(
        session,
        tournament_id=match.tournament_id,
        user_id=result.player_id,
        score_delta=Decimal(result.wins),
        tie_break_delta=Decimal(result.correct_answers),
    )
    await TournamentRoundScoresRepo.upsert_result(
        session,
        payload=TournamentRoundScorePayload(
            tournament_id=match.tournament_id,
            round_number=int(match.round_no),
            player_id=result.player_id,
            opponent_id=result.opponent_id,
            wins=result.wins,
            is_draw=result.is_draw,
            correct_answers=result.correct_answers,
            total_time_ms=result.total_time_ms,
            got_bye=result.got_bye,
            auto_finished=result.auto_finished,
            created_at=created_at,
        ),
    )
