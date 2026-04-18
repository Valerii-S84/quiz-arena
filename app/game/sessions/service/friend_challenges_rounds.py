from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.db.models.friend_challenges import FriendChallenge
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.economy.streak.time import berlin_local_date
from app.game.friend_challenges.constants import (
    DUEL_STATUS_EXPIRED,
    is_duel_playable_for_user,
    normalize_duel_status,
)
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.types import FriendChallengeRoundStartResult, StartSessionResult
from app.game.tournaments.constants import TOURNAMENT_TYPE_DAILY_ARENA

from .friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
)
from .levels import _friend_challenge_level_for_round
from .question_loading import _build_start_result_from_existing_session
from .sessions_start import start_session


@dataclass(slots=True)
class _FriendChallengeRoundContext:
    challenge: FriendChallenge
    has_opponent: bool
    is_creator: bool
    next_round: int


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


def _is_round_playable(context: _FriendChallengeRoundContext) -> bool:
    return is_duel_playable_for_user(
        status=context.challenge.status,
        has_opponent=context.has_opponent,
        is_creator=context.is_creator,
    )


def _build_round_start_result(
    context: _FriendChallengeRoundContext,
    *,
    start_result: StartSessionResult | None,
    waiting_for_opponent: bool,
    already_answered_current_round: bool,
) -> FriendChallengeRoundStartResult:
    return FriendChallengeRoundStartResult(
        snapshot=_build_friend_challenge_snapshot(context.challenge),
        start_result=start_result,
        waiting_for_opponent=waiting_for_opponent,
        already_answered_current_round=already_answered_current_round,
    )


async def _load_round_start_context(
    session: AsyncSession,
    *,
    challenge_id: UUID,
    user_id: int,
    now_utc: datetime,
) -> _FriendChallengeRoundContext:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    if challenge is None:
        raise FriendChallengeNotFoundError

    has_opponent = challenge.opponent_user_id is not None
    challenge.status = normalize_duel_status(
        status=challenge.status,
        has_opponent=has_opponent,
    )
    if _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
        await _emit_friend_challenge_expired_event(
            session,
            challenge=challenge,
            happened_at=now_utc,
            source=EVENT_SOURCE_BOT,
        )
    if challenge.status == DUEL_STATUS_EXPIRED:
        raise FriendChallengeExpiredError

    is_creator = challenge.creator_user_id == user_id
    if not is_creator and challenge.opponent_user_id != user_id:
        raise FriendChallengeAccessError

    context = _FriendChallengeRoundContext(
        challenge=challenge,
        has_opponent=has_opponent,
        is_creator=is_creator,
        next_round=(
            challenge.creator_answered_round if is_creator else challenge.opponent_answered_round
        )
        + 1,
    )
    if not _is_round_playable(context):
        if not has_opponent:
            raise FriendChallengeFullError
        raise FriendChallengeCompletedError
    return context


def _selection_seed(context: _FriendChallengeRoundContext) -> str:
    challenge = context.challenge
    return f"friend:{challenge.id}:{context.next_round}:{challenge.mode_code}"


def _planned_question_id(context: _FriendChallengeRoundContext) -> str | None:
    question_ids = context.challenge.question_ids
    if not question_ids:
        return None
    try:
        return str(question_ids[context.next_round - 1])
    except IndexError:
        return None


async def _apply_header_override(
    session: AsyncSession,
    *,
    start_result: StartSessionResult,
    tournament_match_id: UUID | None,
) -> None:
    start_result.session.header_mode_label_override = await _resolve_question_header_override(
        session,
        tournament_match_id=tournament_match_id,
    )


async def _build_existing_round_start_result(
    session: AsyncSession,
    *,
    context: _FriendChallengeRoundContext,
    existing_round_session: QuizSession,
) -> StartSessionResult:
    start_result = await _build_start_result_from_existing_session(
        session,
        existing=existing_round_session,
        idempotent_replay=True,
    )
    await _apply_header_override(
        session,
        start_result=start_result,
        tournament_match_id=context.challenge.tournament_match_id,
    )
    return start_result


async def _resolve_round_question_id(
    session: AsyncSession,
    *,
    context: _FriendChallengeRoundContext,
    now_utc: datetime,
    selection_seed: str,
    preferred_level: str | None,
) -> str:
    shared_round_session = await QuizSessionsRepo.get_by_friend_challenge_round_any_user(
        session,
        friend_challenge_id=context.challenge.id,
        friend_challenge_round=context.next_round,
    )
    if shared_round_session is not None and shared_round_session.question_id is not None:
        return shared_round_session.question_id

    planned_question_id = _planned_question_id(context)
    if planned_question_id is not None:
        return planned_question_id

    previous_round_question_ids = (
        await QuizSessionsRepo.list_friend_challenge_question_ids_before_round(
            session,
            friend_challenge_id=context.challenge.id,
            before_round=context.next_round,
        )
    )
    from app.game.sessions import service as service_module

    selected_question = await service_module.select_friend_challenge_question(
        session,
        context.challenge.mode_code,
        local_date_berlin=berlin_local_date(now_utc),
        previous_round_question_ids=previous_round_question_ids,
        selection_seed=selection_seed,
        preferred_level=preferred_level,
    )
    return selected_question.question_id


async def _start_new_round_session(
    session: AsyncSession,
    *,
    context: _FriendChallengeRoundContext,
    user_id: int,
    idempotency_key: str,
    now_utc: datetime,
) -> StartSessionResult:
    selection_seed = _selection_seed(context)
    preferred_level = _friend_challenge_level_for_round(round_number=context.next_round)
    start_result = await start_session(
        session,
        user_id=user_id,
        mode_code=context.challenge.mode_code,
        source="FRIEND_CHALLENGE",
        idempotency_key=idempotency_key,
        now_utc=now_utc,
        selection_seed_override=selection_seed,
        preferred_question_level=preferred_level,
        forced_question_id=await _resolve_round_question_id(
            session,
            context=context,
            now_utc=now_utc,
            selection_seed=selection_seed,
            preferred_level=preferred_level,
        ),
        friend_challenge_id=context.challenge.id,
        friend_challenge_round=context.next_round,
        friend_challenge_total_rounds=context.challenge.total_rounds,
    )
    await _apply_header_override(
        session,
        start_result=start_result,
        tournament_match_id=context.challenge.tournament_match_id,
    )
    return start_result


async def start_friend_challenge_round(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    idempotency_key: str,
    now_utc: datetime,
) -> FriendChallengeRoundStartResult:
    context = await _load_round_start_context(
        session,
        challenge_id=challenge_id,
        user_id=user_id,
        now_utc=now_utc,
    )
    if context.next_round > context.challenge.total_rounds:
        return _build_round_start_result(
            context,
            start_result=None,
            waiting_for_opponent=_is_round_playable(context),
            already_answered_current_round=True,
        )

    existing_round_session = await QuizSessionsRepo.get_by_friend_challenge_round_user(
        session,
        friend_challenge_id=context.challenge.id,
        friend_challenge_round=context.next_round,
        user_id=user_id,
    )
    if existing_round_session is not None:
        start_result = await _build_existing_round_start_result(
            session,
            context=context,
            existing_round_session=existing_round_session,
        )
        return _build_round_start_result(
            context,
            start_result=start_result,
            waiting_for_opponent=False,
            already_answered_current_round=False,
        )

    start_result = await _start_new_round_session(
        session,
        context=context,
        user_id=user_id,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
    )
    return _build_round_start_result(
        context,
        start_result=start_result,
        waiting_for_opponent=False,
        already_answered_current_round=False,
    )
