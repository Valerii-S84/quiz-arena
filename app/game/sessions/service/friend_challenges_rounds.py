from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.game.friend_challenges.constants import is_duel_playable_for_user, normalize_duel_status
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.types import FriendChallengeRoundStartResult
from app.game.tournaments.constants import TOURNAMENT_TYPE_DAILY_ARENA

from .friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
)
from .friend_challenges_rounds_result import build_friend_challenge_round_start_result


async def _resolve_question_header_override(
    session: AsyncSession,
    *,
    tournament_match_id: UUID | None,
) -> str | None:
    if tournament_match_id is None:
        return None
    tournament_match = await TournamentMatchesRepo.get_by_id_for_update(
        session, tournament_match_id
    )
    if tournament_match is None:
        return None
    tournament = await TournamentsRepo.get_by_id(session, tournament_match.tournament_id)
    if tournament is None or tournament.type != TOURNAMENT_TYPE_DAILY_ARENA:
        return None
    return "Daily Arena Cup"


async def start_friend_challenge_round(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    idempotency_key: str,
    now_utc: datetime,
) -> FriendChallengeRoundStartResult:
    challenge = await _load_startable_friend_challenge(
        session,
        challenge_id=challenge_id,
        now_utc=now_utc,
    )
    is_creator = _ensure_participant(challenge, user_id=user_id)
    has_opponent = challenge.opponent_user_id is not None
    _ensure_playable_for_user(challenge, has_opponent=has_opponent, is_creator=is_creator)

    next_round = _next_round_for_participant(challenge, is_creator=is_creator)
    if next_round > challenge.total_rounds:
        return _already_answered_result(
            challenge,
            has_opponent=has_opponent,
            is_creator=is_creator,
        )

    header_override = await _resolve_question_header_override(
        session,
        tournament_match_id=challenge.tournament_match_id,
    )
    return await build_friend_challenge_round_start_result(
        session,
        challenge=challenge,
        user_id=user_id,
        next_round=next_round,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
        header_mode_label_override=header_override,
    )


async def _load_startable_friend_challenge(
    session: AsyncSession,
    *,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallenge:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    if challenge is None:
        raise FriendChallengeNotFoundError
    challenge.status = normalize_duel_status(
        status=challenge.status,
        has_opponent=challenge.opponent_user_id is not None,
    )
    if _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
        await _emit_friend_challenge_expired_event(
            session,
            challenge=challenge,
            happened_at=now_utc,
            source=EVENT_SOURCE_BOT,
        )
    if challenge.status == "EXPIRED":
        raise FriendChallengeExpiredError
    return challenge


def _ensure_participant(challenge: FriendChallenge, *, user_id: int) -> bool:
    is_creator = challenge.creator_user_id == user_id
    if not is_creator and challenge.opponent_user_id != user_id:
        raise FriendChallengeAccessError
    return is_creator


def _ensure_playable_for_user(
    challenge: FriendChallenge,
    *,
    has_opponent: bool,
    is_creator: bool,
) -> None:
    if is_duel_playable_for_user(
        status=challenge.status,
        has_opponent=has_opponent,
        is_creator=is_creator,
    ):
        return
    if not has_opponent:
        raise FriendChallengeFullError
    raise FriendChallengeCompletedError


def _next_round_for_participant(challenge: FriendChallenge, *, is_creator: bool) -> int:
    if is_creator:
        return challenge.creator_answered_round + 1
    return challenge.opponent_answered_round + 1


def _already_answered_result(
    challenge: FriendChallenge,
    *,
    has_opponent: bool,
    is_creator: bool,
) -> FriendChallengeRoundStartResult:
    return FriendChallengeRoundStartResult(
        snapshot=_build_friend_challenge_snapshot(challenge),
        start_result=None,
        waiting_for_opponent=is_duel_playable_for_user(
            status=challenge.status,
            has_opponent=has_opponent,
            is_creator=is_creator,
        ),
        already_answered_current_round=True,
    )
