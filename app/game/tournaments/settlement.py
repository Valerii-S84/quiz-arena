from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_WORKER
from app.db.models.tournament_matches import TournamentMatch
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.game.friend_challenges.constants import normalize_duel_status
from app.game.sessions.service.friend_challenges_internal import (
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
)
from app.game.tournaments.constants import (
    TOURNAMENT_MATCH_STATUS_COMPLETED,
    TOURNAMENT_MATCH_STATUS_PENDING,
    TOURNAMENT_MATCH_STATUS_WALKOVER,
)


def _match_scores_from_challenge(
    *,
    match: TournamentMatch,
    challenge_creator_user_id: int,
    challenge_creator_score: int,
    challenge_opponent_score: int,
) -> tuple[int, int]:
    if int(match.user_a) == challenge_creator_user_id:
        return challenge_creator_score, challenge_opponent_score
    return challenge_opponent_score, challenge_creator_score


def _score_deltas_for_match(
    *,
    match_status: str,
    winner_id: int | None,
    user_a: int,
    user_b: int | None,
    score_a: int,
    score_b: int,
) -> list[tuple[int, Decimal, Decimal]]:
    if user_b is None:
        if winner_id == user_a:
            return [(user_a, Decimal("1"), Decimal(score_a))]
        return [(user_a, Decimal("0"), Decimal(score_a))]

    if winner_id == user_a:
        return [
            (user_a, Decimal("1"), Decimal(score_a)),
            (int(user_b), Decimal("0"), Decimal(score_b)),
        ]
    if winner_id == user_b:
        return [
            (user_a, Decimal("0"), Decimal(score_a)),
            (int(user_b), Decimal("1"), Decimal(score_b)),
        ]
    if match_status == TOURNAMENT_MATCH_STATUS_COMPLETED:
        return [
            (user_a, Decimal("0.5"), Decimal(score_a)),
            (int(user_b), Decimal("0.5"), Decimal(score_b)),
        ]
    return [
        (user_a, Decimal("0"), Decimal(score_a)),
        (int(user_b), Decimal("0"), Decimal(score_b)),
    ]


def _valid_winner_for_match(*, match: TournamentMatch, winner_id: int | None) -> int | None:
    allowed: set[int] = {int(match.user_a)}
    if match.user_b is not None:
        allowed.add(int(match.user_b))
    if winner_id is None:
        return None
    return int(winner_id) if int(winner_id) in allowed else None


async def _apply_match_points(
    session: AsyncSession,
    *,
    match: TournamentMatch,
    match_status: str,
    winner_id: int | None,
    score_a: int,
    score_b: int,
) -> None:
    for user_id, score_delta, tie_break_delta in _score_deltas_for_match(
        match_status=match_status,
        winner_id=winner_id,
        user_a=int(match.user_a),
        user_b=(int(match.user_b) if match.user_b is not None else None),
        score_a=score_a,
        score_b=score_b,
    ):
        await TournamentParticipantsRepo.apply_score_delta(
            session,
            tournament_id=match.tournament_id,
            user_id=user_id,
            score_delta=score_delta,
            tie_break_delta=tie_break_delta,
        )


async def settle_pending_match_from_duel(
    session: AsyncSession,
    *,
    match: TournamentMatch,
    now_utc: datetime,
) -> bool:
    if match.status != TOURNAMENT_MATCH_STATUS_PENDING:
        return False
    if match.friend_challenge_id is None:
        match.status = TOURNAMENT_MATCH_STATUS_WALKOVER
        match.winner_id = None
        return True

    challenge_id: UUID = match.friend_challenge_id
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    if challenge is None:
        match.status = TOURNAMENT_MATCH_STATUS_WALKOVER
        match.winner_id = None
        return True

    challenge.status = normalize_duel_status(
        status=challenge.status,
        has_opponent=challenge.opponent_user_id is not None,
    )
    if challenge.expires_at > match.deadline:
        challenge.expires_at = match.deadline
    expired_now = _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc)
    if expired_now:
        await _emit_friend_challenge_expired_event(
            session,
            challenge=challenge,
            happened_at=now_utc,
            source=EVENT_SOURCE_WORKER,
        )

    if challenge.status not in {"COMPLETED", "WALKOVER", "EXPIRED", "CANCELED"}:
        if match.deadline > now_utc:
            return False
        challenge.expires_at = now_utc
        expired_now = _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc)
        if expired_now:
            await _emit_friend_challenge_expired_event(
                session,
                challenge=challenge,
                happened_at=now_utc,
                source=EVENT_SOURCE_WORKER,
            )
        if challenge.status not in {"COMPLETED", "WALKOVER", "EXPIRED", "CANCELED"}:
            return False

    score_a, score_b = _match_scores_from_challenge(
        match=match,
        challenge_creator_user_id=int(challenge.creator_user_id),
        challenge_creator_score=int(challenge.creator_score),
        challenge_opponent_score=int(challenge.opponent_score),
    )
    winner_id = _valid_winner_for_match(
        match=match,
        winner_id=(int(challenge.winner_user_id) if challenge.winner_user_id is not None else None),
    )
    match_status = (
        TOURNAMENT_MATCH_STATUS_COMPLETED
        if challenge.status == "COMPLETED"
        else TOURNAMENT_MATCH_STATUS_WALKOVER
    )
    await _apply_match_points(
        session,
        match=match,
        match_status=match_status,
        winner_id=winner_id,
        score_a=score_a,
        score_b=score_b,
    )
    match.status = match_status
    match.winner_id = winner_id
    return True
