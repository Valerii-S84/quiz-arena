from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.quiz_attempts_repo import QuizAttemptsRepo as _QuizAttemptsRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.economy.energy.service import EnergyService as _EnergyService
from app.economy.streak.time import berlin_local_date
from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.duels.limits import DuelLimitService
from app.game.sessions.errors import FriendChallengeAccessError
from app.game.sessions.types import SessionQuestionView, StartSessionResult

from .levels import _is_persistent_adaptive_mode
from .progression import resolve_start_progression_state, select_level_weighted
from .question_loading import _build_start_result_from_existing_session
from .sessions_start_arena import ArenaAttemptsRepo as _ArenaAttemptsRepo
from .sessions_start_arena import (
    _arena_attempt_started_before_expiry as _arena_attempt_started_before_expiry_impl,
)
from .sessions_start_arena import _arena_duel_question_id as _arena_duel_question_id_impl
from .sessions_start_arena import (
    _ensure_arena_attempt_can_start as _ensure_arena_attempt_can_start_impl,
)
from .sessions_start_arena import (
    _ensure_arena_duel_allows_attempt_start as _ensure_arena_duel_allows_attempt_start_impl,
)
from .sessions_start_daily import start_daily_session
from .sessions_start_existing import (
    _ensure_existing_session_matches_start_request as _ensure_existing_session_matches_start_request_impl,
)
from .sessions_start_existing import _session_question_number as _session_question_number_impl
from .sessions_start_existing import _session_total_questions as _session_total_questions_impl
from .sessions_start_existing import get_session_user_id as _get_session_user_id_impl
from .sessions_start_runtime import (
    _consume_start_energy_if_needed,
    _create_started_session,
    _resolve_start_question,
)

QuizAttemptsRepo = _QuizAttemptsRepo
EnergyService = _EnergyService
ArenaAttemptsRepo = _ArenaAttemptsRepo
get_session_user_id = _get_session_user_id_impl
_session_question_number = _session_question_number_impl
_session_total_questions = _session_total_questions_impl
_ensure_existing_session_matches_start_request = _ensure_existing_session_matches_start_request_impl
_ensure_arena_attempt_can_start = _ensure_arena_attempt_can_start_impl
_ensure_arena_duel_allows_attempt_start = _ensure_arena_duel_allows_attempt_start_impl
_arena_attempt_started_before_expiry = _arena_attempt_started_before_expiry_impl
_arena_duel_question_id = _arena_duel_question_id_impl


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
    recent_question_ids_override: tuple[str, ...] | None = None,
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
            or not 1 <= arena_round <= DUEL_QUESTION_COUNT
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

    energy_free, energy_paid, energy_cost_total = await _consume_start_energy_if_needed(
        session,
        user_id=user_id,
        source=source,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
    )
    question = await _resolve_start_question(
        session,
        user_id=user_id,
        mode_code=mode_code,
        source=source,
        local_date=local_date,
        selection_seed_override=selection_seed_override,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
        forced_question_id=resolved_forced_question_id,
        preferred_question_level=preferred_question_level,
        recent_question_ids_override=recent_question_ids_override,
        resolve_start_progression_state=resolve_start_progression_state,
        select_level_weighted=select_level_weighted,
        is_persistent_adaptive_mode=_is_persistent_adaptive_mode,
    )
    created = await _create_started_session(
        session,
        user_id=user_id,
        mode_code=mode_code,
        source=source,
        question=question,
        energy_cost_total=energy_cost_total,
        now_utc=now_utc,
        local_date=local_date,
        idempotency_key=idempotency_key,
        friend_challenge_id=friend_challenge_id,
        friend_challenge_round=friend_challenge_round,
        arena_attempt_id=arena_attempt_id,
        arena_round=arena_round,
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
