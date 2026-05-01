from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_sessions import QuizSession
from app.db.repo.arena_attempts_repo import ArenaAttemptsRepo
from app.db.repo.quiz_attempts_repo import QuizAttemptsRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.economy.energy.service import EnergyService
from app.economy.streak.time import berlin_local_date
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_ROLE_CHALLENGER,
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_DUEL_STATUS_DRAFT,
)
from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.duels.limits import DuelLimitService
from app.game.modes.rules import is_zero_cost_source
from app.game.questions.types import QuizQuestion
from app.game.sessions.errors import (
    EnergyInsufficientError,
    FriendChallengeAccessError,
    SessionNotFoundError,
)
from app.game.sessions.types import SessionQuestionView, StartSessionResult

from .levels import _is_persistent_adaptive_mode
from .progression import resolve_start_progression_state, select_level_weighted
from .question_loading import _build_start_result_from_existing_session
from .sessions_start_daily import start_daily_session

_ARENA_START_ROLES = frozenset(
    {
        ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
        ARENA_ATTEMPT_ROLE_CHALLENGER,
    }
)


async def start_session(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    idempotency_key: str,
    now_utc: datetime,
    selection_seed_override: str | None = None,
    preferred_question_level: str | None = None,
    forced_question_id: str | None = None,
    friend_challenge_id: UUID | None = None,
    friend_challenge_round: int | None = None,
    friend_challenge_total_rounds: int | None = None,
    arena_attempt_id: UUID | None = None,
    arena_round: int | None = None,
    duel_limit_checked: bool = False,
) -> StartSessionResult:
    existing = await QuizSessionsRepo.get_by_idempotency_key(session, idempotency_key)
    local_date = berlin_local_date(now_utc)
    resolved_forced_question_id = forced_question_id
    if existing is not None:
        _ensure_existing_session_matches_start_request(
            existing,
            user_id=user_id,
            mode_code=mode_code,
            source=source,
            friend_challenge_id=friend_challenge_id,
            friend_challenge_round=friend_challenge_round,
            arena_attempt_id=arena_attempt_id,
            arena_round=arena_round,
        )
        return await _build_start_result_from_existing_session(
            session,
            existing=existing,
            idempotent_replay=True,
        )

    DuelLimitService.assert_start_gate(source, duel_limit_checked=duel_limit_checked)
    if source == "FRIEND_CHALLENGE" and (
        friend_challenge_id is None or friend_challenge_round is None
    ):
        raise FriendChallengeAccessError
    if source == "ARENA_DUEL":
        if (
            arena_attempt_id is None
            or arena_round is None
            or arena_round < 1
            or arena_round > DUEL_QUESTION_COUNT
        ):
            raise FriendChallengeAccessError
        resolved_forced_question_id = await _ensure_arena_attempt_can_start(
            session,
            arena_attempt_id=arena_attempt_id,
            user_id=user_id,
            mode_code=mode_code,
            arena_round=arena_round,
            forced_question_id=forced_question_id,
            now_utc=now_utc,
        )

    if source == "DAILY_CHALLENGE":
        return await start_daily_session(
            session,
            user_id=user_id,
            idempotency_key=idempotency_key,
            local_date=local_date,
            now_utc=now_utc,
        )

    energy_free = 0
    energy_paid = 0
    energy_cost_total = 0
    if not is_zero_cost_source(source):
        energy_result = await EnergyService.consume_quiz(
            session,
            user_id=user_id,
            idempotency_key=f"energy:{idempotency_key}",
            now_utc=now_utc,
        )
        if not energy_result.allowed:
            raise EnergyInsufficientError
        energy_free = energy_result.free_energy
        energy_paid = energy_result.paid_energy
        energy_cost_total = 1

    question: QuizQuestion | None = None
    if resolved_forced_question_id is not None:
        from app.game.sessions import service as service_module

        question = await service_module.get_question_by_id(
            session,
            mode_code,
            question_id=resolved_forced_question_id,
            local_date_berlin=local_date,
        )
    if source == "ARENA_DUEL" and question is None:
        raise FriendChallengeAccessError

    if question is None:
        effective_preferred_level = preferred_question_level
        allowed_levels: tuple[str, ...] | None = None
        mix_step = 0
        if _is_persistent_adaptive_mode(mode_code=mode_code):
            (
                effective_preferred_level,
                mix_step,
                allowed_levels,
            ) = await resolve_start_progression_state(
                session,
                user_id=user_id,
                mode_code=mode_code,
                preferred_level_override=effective_preferred_level,
                now_utc=now_utc,
            )

        recent_question_ids: list[str] = []
        if source != "FRIEND_CHALLENGE":
            recent_question_ids = await QuizAttemptsRepo.get_recent_question_ids_for_mode(
                session,
                user_id=user_id,
                mode_code=mode_code,
                limit=20,
            )
        selection_seed = selection_seed_override or idempotency_key
        if (
            _is_persistent_adaptive_mode(mode_code=mode_code)
            and effective_preferred_level is not None
        ):
            effective_preferred_level = select_level_weighted(
                effective_preferred_level,
                mix_step,
                selection_seed=selection_seed,
            )
        from app.game.sessions import service as service_module

        question = await service_module.select_question_for_mode(
            session,
            mode_code,
            local_date_berlin=local_date,
            recent_question_ids=recent_question_ids,
            selection_seed=selection_seed,
            preferred_level=effective_preferred_level,
            allowed_levels=allowed_levels,
        )

    created = await QuizSessionsRepo.create(
        session,
        quiz_session=QuizSession(
            id=uuid4(),
            user_id=user_id,
            mode_code=mode_code,
            source=source,
            status="STARTED",
            energy_cost_total=energy_cost_total,
            question_id=question.question_id,
            friend_challenge_id=friend_challenge_id,
            friend_challenge_round=friend_challenge_round,
            arena_attempt_id=arena_attempt_id,
            arena_round=arena_round,
            started_at=now_utc,
            local_date_berlin=local_date,
            idempotency_key=idempotency_key,
        ),
    )

    return StartSessionResult(
        session=SessionQuestionView(
            session_id=created.id,
            question_id=question.question_id,
            text=question.text,
            options=question.options,
            mode_code=mode_code,
            source=source,
            category=question.category,
            question_number=_session_question_number(
                source=source,
                friend_challenge_round=friend_challenge_round,
                arena_round=arena_round,
            ),
            total_questions=_session_total_questions(
                source=source,
                friend_challenge_total_rounds=friend_challenge_total_rounds,
            ),
        ),
        energy_free=energy_free,
        energy_paid=energy_paid,
        idempotent_replay=False,
    )


async def get_session_user_id(session: AsyncSession, session_id: UUID) -> int:
    quiz_session = await QuizSessionsRepo.get_by_id(session, session_id)
    if quiz_session is None:
        raise SessionNotFoundError
    return quiz_session.user_id


def _session_question_number(
    *,
    source: str,
    friend_challenge_round: int | None,
    arena_round: int | None,
) -> int:
    if source == "FRIEND_CHALLENGE":
        return friend_challenge_round or 1
    if source == "ARENA_DUEL":
        return arena_round or 1
    return 1


def _session_total_questions(
    *,
    source: str,
    friend_challenge_total_rounds: int | None,
) -> int:
    if source == "FRIEND_CHALLENGE":
        return friend_challenge_total_rounds or 1
    if source == "ARENA_DUEL":
        return DUEL_QUESTION_COUNT
    return 1


def _ensure_existing_session_matches_start_request(
    existing: QuizSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    friend_challenge_id: UUID | None,
    friend_challenge_round: int | None,
    arena_attempt_id: UUID | None,
    arena_round: int | None,
) -> None:
    if existing.user_id != user_id or existing.mode_code != mode_code or existing.source != source:
        raise FriendChallengeAccessError

    if source == "FRIEND_CHALLENGE":
        if (
            friend_challenge_id is None
            or friend_challenge_round is None
            or existing.friend_challenge_id != friend_challenge_id
            or existing.friend_challenge_round != friend_challenge_round
        ):
            raise FriendChallengeAccessError
        return

    if source == "ARENA_DUEL":
        if (
            arena_attempt_id is None
            or arena_round is None
            or existing.arena_attempt_id != arena_attempt_id
            or existing.arena_round != arena_round
        ):
            raise FriendChallengeAccessError


async def _ensure_arena_attempt_can_start(
    session: AsyncSession,
    *,
    arena_attempt_id: UUID,
    user_id: int,
    mode_code: str,
    arena_round: int,
    forced_question_id: str | None,
    now_utc: datetime,
) -> str:
    context = await ArenaAttemptsRepo.get_start_context_for_update(session, arena_attempt_id)
    if context is None:
        raise FriendChallengeAccessError

    attempt = context.attempt
    if (
        attempt.user_id != user_id
        or attempt.role not in _ARENA_START_ROLES
        or attempt.score is not None
        or attempt.time_ms is not None
        or attempt.result is not None
        or attempt.completed_at is not None
    ):
        raise FriendChallengeAccessError

    duel = context.duel
    _ensure_arena_duel_allows_attempt_start(
        duel=duel,
        attempt_role=attempt.role,
        now_utc=now_utc,
    )
    expected_question_id = _arena_duel_question_id(duel.question_ids, arena_round)
    if duel.mode_code != mode_code or expected_question_id is None:
        raise FriendChallengeAccessError
    if forced_question_id is not None and forced_question_id != expected_question_id:
        raise FriendChallengeAccessError
    return expected_question_id


def _ensure_arena_duel_allows_attempt_start(
    *,
    duel: object,
    attempt_role: str,
    now_utc: datetime,
) -> None:
    expires_at = getattr(duel, "expires_at", None)
    if not isinstance(expires_at, datetime) or expires_at <= now_utc:
        raise FriendChallengeAccessError

    status = getattr(duel, "status", None)
    if attempt_role == ARENA_ATTEMPT_ROLE_CREATOR_BASELINE:
        if status != ARENA_DUEL_STATUS_DRAFT:
            raise FriendChallengeAccessError
        return
    if attempt_role == ARENA_ATTEMPT_ROLE_CHALLENGER and status == ARENA_DUEL_STATUS_ACTIVE:
        return
    raise FriendChallengeAccessError


def _arena_duel_question_id(question_ids: object, arena_round: int) -> str | None:
    if not isinstance(question_ids, list):
        return None
    try:
        question_id = question_ids[arena_round - 1]
    except IndexError:
        return None
    if not isinstance(question_id, str) or not question_id:
        return None
    return question_id
