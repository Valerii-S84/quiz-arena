from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.friend_challenges import FriendChallenge
from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.mode_access_repo import ModeAccessRepo
from app.db.repo.mode_progress_repo import ModeProgressRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.quiz_attempts_repo import QuizAttemptsRepo
from app.db.repo.quiz_questions_repo import QuizQuestionsRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.db.repo.users_repo import UsersRepo
from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.economy.energy.service import EnergyService
from app.economy.streak.service import StreakService
from app.economy.streak.time import berlin_local_date
from app.game.modes.rules import is_mode_allowed, is_zero_cost_source
from app.game.questions.runtime_bank import (
    get_question_by_id,
    get_question_for_mode,
    select_friend_challenge_question,
    select_question_for_mode,
)
from app.game.questions.types import QuizQuestion
from app.game.sessions.errors import (
    DailyChallengeAlreadyPlayedError,
    EnergyInsufficientError,
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
    FriendChallengePaymentRequiredError,
    InvalidAnswerOptionError,
    ModeLockedError,
    SessionNotFoundError,
)
from app.game.sessions.types import (
    AnswerSessionResult,
    FriendChallengeJoinResult,
    FriendChallengeRoundStartResult,
    FriendChallengeSnapshot,
    SessionQuestionView,
    StartSessionResult,
)

FRIEND_CHALLENGE_TOTAL_ROUNDS = 12
FRIEND_CHALLENGE_FREE_CREATES = 2
FRIEND_CHALLENGE_TICKET_PRODUCT_CODE = "FRIEND_CHALLENGE_5"
FRIEND_CHALLENGE_TTL_SECONDS = max(60, int(get_settings().friend_challenge_ttl_seconds))
FRIEND_CHALLENGE_LEVEL_SEQUENCE: tuple[str, ...] = (
    "A1",
    "A1",
    "A1",
    "A2",
    "A2",
    "A2",
    "A2",
    "A2",
    "A2",
    "B1",
    "B1",
    "B1",
)
LEVEL_ORDER: tuple[str, ...] = ("A1", "A2", "B1", "B2", "C1", "C2")
PERSISTENT_ADAPTIVE_MODE_BOUNDS: dict[str, tuple[str, str]] = {
    "ARTIKEL_SPRINT": ("A1", "B2"),
}


class GameSessionService:
    @staticmethod
    def _friend_challenge_expires_at(*, now_utc: datetime) -> datetime:
        return now_utc + timedelta(seconds=FRIEND_CHALLENGE_TTL_SECONDS)

    @staticmethod
    def _expire_friend_challenge_if_due(*, challenge: FriendChallenge, now_utc: datetime) -> bool:
        if challenge.status != "ACTIVE":
            return False
        if challenge.expires_at > now_utc:
            return False
        challenge.status = "EXPIRED"
        challenge.winner_user_id = None
        challenge.completed_at = now_utc
        challenge.updated_at = now_utc
        return True

    @staticmethod
    async def _emit_friend_challenge_expired_event(
        session: AsyncSession,
        *,
        challenge: FriendChallenge,
        happened_at: datetime,
        source: str,
    ) -> None:
        await emit_analytics_event(
            session,
            event_type="friend_challenge_expired",
            source=source,
            happened_at=happened_at,
            user_id=None,
            payload={
                "challenge_id": str(challenge.id),
                "creator_user_id": challenge.creator_user_id,
                "opponent_user_id": challenge.opponent_user_id,
                "creator_score": challenge.creator_score,
                "opponent_score": challenge.opponent_score,
                "total_rounds": challenge.total_rounds,
                "expires_at": challenge.expires_at.isoformat(),
            },
        )

    @staticmethod
    async def _resolve_friend_challenge_access_type(
        session: AsyncSession,
        *,
        creator_user_id: int,
        now_utc: datetime,
    ) -> str:
        creator = await UsersRepo.get_by_id_for_update(session, creator_user_id)
        if creator is None:
            raise FriendChallengeAccessError

        premium_active = await EntitlementsRepo.has_active_premium(session, creator_user_id, now_utc)
        access_type = "PREMIUM"
        if not premium_active:
            free_count = await FriendChallengesRepo.count_by_creator_access_type(
                session,
                creator_user_id=creator_user_id,
                access_type="FREE",
            )
            if free_count < FRIEND_CHALLENGE_FREE_CREATES:
                access_type = "FREE"
            else:
                paid_count = await FriendChallengesRepo.count_by_creator_access_type(
                    session,
                    creator_user_id=creator_user_id,
                    access_type="PAID_TICKET",
                )
                paid_tickets = await PurchasesRepo.count_credited_product(
                    session,
                    user_id=creator_user_id,
                    product_code=FRIEND_CHALLENGE_TICKET_PRODUCT_CODE,
                )
                if paid_count >= paid_tickets:
                    raise FriendChallengePaymentRequiredError
                access_type = "PAID_TICKET"
        return access_type

    @staticmethod
    async def _create_friend_challenge_row(
        session: AsyncSession,
        *,
        creator_user_id: int,
        opponent_user_id: int | None,
        mode_code: str,
        access_type: str,
        total_rounds: int,
        now_utc: datetime,
        series_id: UUID | None = None,
        series_game_number: int = 1,
        series_best_of: int = 1,
    ) -> FriendChallenge:
        challenge = await FriendChallengesRepo.create(
            session,
            challenge=FriendChallenge(
                id=uuid4(),
                invite_token=uuid4().hex,
                creator_user_id=creator_user_id,
                opponent_user_id=opponent_user_id,
                mode_code=mode_code,
                access_type=access_type,
                status="ACTIVE",
                current_round=1,
                total_rounds=max(1, total_rounds),
                series_id=series_id,
                series_game_number=max(1, int(series_game_number)),
                series_best_of=max(1, int(series_best_of)),
                creator_score=0,
                opponent_score=0,
                creator_answered_round=0,
                opponent_answered_round=0,
                winner_user_id=None,
                expires_at=GameSessionService._friend_challenge_expires_at(now_utc=now_utc),
                expires_last_chance_notified_at=None,
                created_at=now_utc,
                updated_at=now_utc,
                completed_at=None,
            ),
        )
        return challenge

    @staticmethod
    def _build_friend_challenge_snapshot(challenge: FriendChallenge) -> FriendChallengeSnapshot:
        return FriendChallengeSnapshot(
            challenge_id=challenge.id,
            invite_token=challenge.invite_token,
            mode_code=challenge.mode_code,
            access_type=challenge.access_type,
            status=challenge.status,
            creator_user_id=challenge.creator_user_id,
            opponent_user_id=challenge.opponent_user_id,
            current_round=challenge.current_round,
            total_rounds=challenge.total_rounds,
            series_id=challenge.series_id,
            series_game_number=challenge.series_game_number,
            series_best_of=challenge.series_best_of,
            creator_score=challenge.creator_score,
            opponent_score=challenge.opponent_score,
            winner_user_id=challenge.winner_user_id,
            expires_at=challenge.expires_at,
        )

    @staticmethod
    def _series_wins_needed(*, best_of: int) -> int:
        resolved_best_of = max(1, int(best_of))
        return (resolved_best_of // 2) + 1

    @staticmethod
    def _count_series_wins(
        *,
        series_challenges: list[FriendChallenge],
        creator_user_id: int,
        opponent_user_id: int | None,
    ) -> tuple[int, int]:
        creator_wins = 0
        opponent_wins = 0
        for item in series_challenges:
            if item.status not in {"COMPLETED", "EXPIRED"}:
                continue
            if item.winner_user_id == creator_user_id:
                creator_wins += 1
            elif opponent_user_id is not None and item.winner_user_id == opponent_user_id:
                opponent_wins += 1
        return creator_wins, opponent_wins

    @staticmethod
    def _normalize_level(level: str | None) -> str | None:
        if level is None:
            return None
        normalized = level.strip().upper()
        return normalized or None

    @staticmethod
    def _is_persistent_adaptive_mode(*, mode_code: str) -> bool:
        return mode_code in PERSISTENT_ADAPTIVE_MODE_BOUNDS

    @staticmethod
    def _clamp_level_for_mode(*, mode_code: str, level: str | None) -> str | None:
        normalized = GameSessionService._normalize_level(level)
        bounds = PERSISTENT_ADAPTIVE_MODE_BOUNDS.get(mode_code)
        if bounds is None:
            return normalized

        min_level, max_level = bounds
        min_index = LEVEL_ORDER.index(min_level)
        max_index = LEVEL_ORDER.index(max_level)
        if normalized is None or normalized not in LEVEL_ORDER:
            return LEVEL_ORDER[min_index]
        level_index = LEVEL_ORDER.index(normalized)
        clamped_index = min(max_index, max(min_index, level_index))
        return LEVEL_ORDER[clamped_index]

    @staticmethod
    def _next_preferred_level(
        *,
        question_level: str | None,
        is_correct: bool,
        mode_code: str | None = None,
    ) -> str | None:
        normalized = GameSessionService._normalize_level(question_level)
        if normalized is None:
            return None
        if normalized not in LEVEL_ORDER:
            return None
        if not is_correct:
            next_level = normalized
        else:
            current_index = LEVEL_ORDER.index(normalized)
            if current_index >= len(LEVEL_ORDER) - 1:
                next_level = normalized
            else:
                next_level = LEVEL_ORDER[current_index + 1]

        if mode_code is None:
            return next_level
        return GameSessionService._clamp_level_for_mode(
            mode_code=mode_code,
            level=next_level,
        )

    @staticmethod
    def _friend_challenge_level_for_round(*, round_number: int) -> str | None:
        if round_number <= 0:
            return None
        if round_number <= len(FRIEND_CHALLENGE_LEVEL_SEQUENCE):
            return FRIEND_CHALLENGE_LEVEL_SEQUENCE[round_number - 1]
        return FRIEND_CHALLENGE_LEVEL_SEQUENCE[-1]

    @staticmethod
    async def _infer_preferred_level_from_recent_attempt(
        session: AsyncSession,
        *,
        user_id: int,
        mode_code: str,
    ) -> str | None:
        recent_question_ids = await QuizAttemptsRepo.get_recent_question_ids_for_mode(
            session,
            user_id=user_id,
            mode_code=mode_code,
            limit=1,
        )
        if not recent_question_ids:
            return None

        latest_question = await QuizQuestionsRepo.get_by_id(session, recent_question_ids[0])
        if latest_question is None or latest_question.status != "ACTIVE":
            return None

        return GameSessionService._normalize_level(latest_question.level)

    @staticmethod
    async def _load_question_for_session(
        session: AsyncSession,
        *,
        quiz_session: QuizSession,
    ) -> QuizQuestion:
        question = None
        if quiz_session.question_id is not None:
            question = await get_question_by_id(
                session,
                quiz_session.mode_code,
                question_id=quiz_session.question_id,
                local_date_berlin=quiz_session.local_date_berlin,
            )
        if question is not None:
            return question
        return await get_question_for_mode(
            session,
            quiz_session.mode_code,
            local_date_berlin=quiz_session.local_date_berlin,
        )

    @staticmethod
    async def _build_start_result_from_existing_session(
        session: AsyncSession,
        *,
        existing: QuizSession,
        idempotent_replay: bool,
    ) -> StartSessionResult:
        question = await GameSessionService._load_question_for_session(session, quiz_session=existing)
        total_questions: int | None = None
        question_number: int | None = None
        if existing.source == "FRIEND_CHALLENGE":
            question_number = existing.friend_challenge_round
            if existing.friend_challenge_id is not None:
                challenge = await FriendChallengesRepo.get_by_id(session, existing.friend_challenge_id)
                if challenge is not None:
                    total_questions = challenge.total_rounds
        return StartSessionResult(
            session=SessionQuestionView(
                session_id=existing.id,
                question_id=question.question_id,
                text=question.text,
                options=question.options,
                mode_code=existing.mode_code,
                source=existing.source,
                category=question.category,
                question_number=question_number,
                total_questions=total_questions,
            ),
            energy_free=0,
            energy_paid=0,
            idempotent_replay=idempotent_replay,
        )

    @staticmethod
    def _resolve_challenge_opponent_user_id(
        *,
        challenge: FriendChallenge,
        initiator_user_id: int,
    ) -> int:
        if challenge.creator_user_id == initiator_user_id:
            opponent_user_id = challenge.opponent_user_id
        else:
            opponent_user_id = challenge.creator_user_id
        if opponent_user_id is None:
            raise FriendChallengeAccessError
        return opponent_user_id

    @staticmethod
    async def create_friend_challenge(
        session: AsyncSession,
        *,
        creator_user_id: int,
        mode_code: str,
        now_utc: datetime,
        total_rounds: int = FRIEND_CHALLENGE_TOTAL_ROUNDS,
    ) -> FriendChallengeSnapshot:
        access_type = await GameSessionService._resolve_friend_challenge_access_type(
            session,
            creator_user_id=creator_user_id,
            now_utc=now_utc,
        )
        challenge = await GameSessionService._create_friend_challenge_row(
            session,
            creator_user_id=creator_user_id,
            opponent_user_id=None,
            mode_code=mode_code,
            access_type=access_type,
            total_rounds=total_rounds,
            now_utc=now_utc,
        )
        await emit_analytics_event(
            session,
            event_type="friend_challenge_created",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=creator_user_id,
            payload={
                "challenge_id": str(challenge.id),
                "mode_code": challenge.mode_code,
                "access_type": challenge.access_type,
                "total_rounds": challenge.total_rounds,
                "entrypoint": "standard",
                "expires_at": challenge.expires_at.isoformat(),
                "series_id": None,
                "series_game_number": challenge.series_game_number,
                "series_best_of": challenge.series_best_of,
            },
        )
        return GameSessionService._build_friend_challenge_snapshot(challenge)

    @staticmethod
    async def create_friend_challenge_rematch(
        session: AsyncSession,
        *,
        initiator_user_id: int,
        challenge_id: UUID,
        now_utc: datetime,
    ) -> FriendChallengeSnapshot:
        challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
        if challenge is None:
            raise FriendChallengeNotFoundError
        if GameSessionService._expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
            await GameSessionService._emit_friend_challenge_expired_event(
                session,
                challenge=challenge,
                happened_at=now_utc,
                source=EVENT_SOURCE_BOT,
            )
        if challenge.status not in {"COMPLETED", "EXPIRED"}:
            raise FriendChallengeAccessError
        if initiator_user_id not in {challenge.creator_user_id, challenge.opponent_user_id}:
            raise FriendChallengeAccessError

        opponent_user_id = GameSessionService._resolve_challenge_opponent_user_id(
            challenge=challenge,
            initiator_user_id=initiator_user_id,
        )

        series_id = challenge.series_id
        series_game_number = 1
        series_best_of = 1
        if series_id is not None and challenge.series_best_of > 1:
            series_challenges = await FriendChallengesRepo.list_by_series_id_for_update(
                session,
                series_id=series_id,
            )
            creator_wins, opponent_wins = GameSessionService._count_series_wins(
                series_challenges=series_challenges,
                creator_user_id=challenge.creator_user_id,
                opponent_user_id=challenge.opponent_user_id,
            )
            wins_needed = GameSessionService._series_wins_needed(best_of=challenge.series_best_of)
            max_wins = max(creator_wins, opponent_wins)
            max_game_number = max(
                (int(item.series_game_number) for item in series_challenges),
                default=int(challenge.series_game_number),
            )
            if max_wins < wins_needed and max_game_number < challenge.series_best_of:
                series_game_number = max_game_number + 1
                series_best_of = challenge.series_best_of
            else:
                series_id = None

        access_type = await GameSessionService._resolve_friend_challenge_access_type(
            session,
            creator_user_id=initiator_user_id,
            now_utc=now_utc,
        )
        rematch = await GameSessionService._create_friend_challenge_row(
            session,
            creator_user_id=initiator_user_id,
            opponent_user_id=opponent_user_id,
            mode_code=challenge.mode_code,
            access_type=access_type,
            total_rounds=challenge.total_rounds,
            now_utc=now_utc,
            series_id=series_id,
            series_game_number=series_game_number,
            series_best_of=series_best_of,
        )
        await emit_analytics_event(
            session,
            event_type="friend_challenge_created",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=initiator_user_id,
            payload={
                "challenge_id": str(rematch.id),
                "mode_code": rematch.mode_code,
                "access_type": rematch.access_type,
                "total_rounds": rematch.total_rounds,
                "entrypoint": "rematch",
                "source_challenge_id": str(challenge_id),
                "expires_at": rematch.expires_at.isoformat(),
                "series_id": str(rematch.series_id) if rematch.series_id is not None else None,
                "series_game_number": rematch.series_game_number,
                "series_best_of": rematch.series_best_of,
            },
        )
        await emit_analytics_event(
            session,
            event_type="friend_challenge_rematch_created",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=initiator_user_id,
            payload={
                "challenge_id": str(rematch.id),
                "source_challenge_id": str(challenge_id),
                "opponent_user_id": opponent_user_id,
                "total_rounds": rematch.total_rounds,
                "expires_at": rematch.expires_at.isoformat(),
                "series_id": str(rematch.series_id) if rematch.series_id is not None else None,
                "series_game_number": rematch.series_game_number,
                "series_best_of": rematch.series_best_of,
            },
        )
        return GameSessionService._build_friend_challenge_snapshot(rematch)

    @staticmethod
    async def create_friend_challenge_best_of_three(
        session: AsyncSession,
        *,
        initiator_user_id: int,
        challenge_id: UUID,
        now_utc: datetime,
        best_of: int = 3,
    ) -> FriendChallengeSnapshot:
        challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
        if challenge is None:
            raise FriendChallengeNotFoundError
        if GameSessionService._expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
            await GameSessionService._emit_friend_challenge_expired_event(
                session,
                challenge=challenge,
                happened_at=now_utc,
                source=EVENT_SOURCE_BOT,
            )
        if challenge.status not in {"COMPLETED", "EXPIRED"}:
            raise FriendChallengeAccessError
        if initiator_user_id not in {challenge.creator_user_id, challenge.opponent_user_id}:
            raise FriendChallengeAccessError

        opponent_user_id = GameSessionService._resolve_challenge_opponent_user_id(
            challenge=challenge,
            initiator_user_id=initiator_user_id,
        )
        resolved_best_of = max(1, int(best_of))

        access_type = await GameSessionService._resolve_friend_challenge_access_type(
            session,
            creator_user_id=initiator_user_id,
            now_utc=now_utc,
        )
        series_id = uuid4()
        duel = await GameSessionService._create_friend_challenge_row(
            session,
            creator_user_id=initiator_user_id,
            opponent_user_id=opponent_user_id,
            mode_code=challenge.mode_code,
            access_type=access_type,
            total_rounds=challenge.total_rounds,
            now_utc=now_utc,
            series_id=series_id,
            series_game_number=1,
            series_best_of=resolved_best_of,
        )
        await emit_analytics_event(
            session,
            event_type="friend_challenge_created",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=initiator_user_id,
            payload={
                "challenge_id": str(duel.id),
                "mode_code": duel.mode_code,
                "access_type": duel.access_type,
                "total_rounds": duel.total_rounds,
                "entrypoint": "best_of_series",
                "source_challenge_id": str(challenge_id),
                "series_id": str(series_id),
                "series_game_number": duel.series_game_number,
                "series_best_of": duel.series_best_of,
                "expires_at": duel.expires_at.isoformat(),
            },
        )
        await emit_analytics_event(
            session,
            event_type="friend_challenge_series_started",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=initiator_user_id,
            payload={
                "challenge_id": str(duel.id),
                "source_challenge_id": str(challenge_id),
                "opponent_user_id": opponent_user_id,
                "series_id": str(series_id),
                "series_game_number": duel.series_game_number,
                "series_best_of": duel.series_best_of,
            },
        )
        return GameSessionService._build_friend_challenge_snapshot(duel)

    @staticmethod
    async def create_friend_challenge_series_next_game(
        session: AsyncSession,
        *,
        initiator_user_id: int,
        challenge_id: UUID,
        now_utc: datetime,
    ) -> FriendChallengeSnapshot:
        challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
        if challenge is None:
            raise FriendChallengeNotFoundError
        if GameSessionService._expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
            await GameSessionService._emit_friend_challenge_expired_event(
                session,
                challenge=challenge,
                happened_at=now_utc,
                source=EVENT_SOURCE_BOT,
            )
        if challenge.status not in {"COMPLETED", "EXPIRED"}:
            raise FriendChallengeAccessError
        if initiator_user_id not in {challenge.creator_user_id, challenge.opponent_user_id}:
            raise FriendChallengeAccessError
        if challenge.series_id is None or challenge.series_best_of <= 1:
            raise FriendChallengeAccessError

        series_challenges = await FriendChallengesRepo.list_by_series_id_for_update(
            session,
            series_id=challenge.series_id,
        )
        creator_wins, opponent_wins = GameSessionService._count_series_wins(
            series_challenges=series_challenges,
            creator_user_id=challenge.creator_user_id,
            opponent_user_id=challenge.opponent_user_id,
        )
        wins_needed = GameSessionService._series_wins_needed(best_of=challenge.series_best_of)
        max_wins = max(creator_wins, opponent_wins)
        max_game_number = max(
            (int(item.series_game_number) for item in series_challenges),
            default=int(challenge.series_game_number),
        )
        if max_wins >= wins_needed or max_game_number >= challenge.series_best_of:
            raise FriendChallengeAccessError

        opponent_user_id = GameSessionService._resolve_challenge_opponent_user_id(
            challenge=challenge,
            initiator_user_id=initiator_user_id,
        )
        access_type = await GameSessionService._resolve_friend_challenge_access_type(
            session,
            creator_user_id=initiator_user_id,
            now_utc=now_utc,
        )
        duel = await GameSessionService._create_friend_challenge_row(
            session,
            creator_user_id=initiator_user_id,
            opponent_user_id=opponent_user_id,
            mode_code=challenge.mode_code,
            access_type=access_type,
            total_rounds=challenge.total_rounds,
            now_utc=now_utc,
            series_id=challenge.series_id,
            series_game_number=max_game_number + 1,
            series_best_of=challenge.series_best_of,
        )
        await emit_analytics_event(
            session,
            event_type="friend_challenge_created",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=initiator_user_id,
            payload={
                "challenge_id": str(duel.id),
                "mode_code": duel.mode_code,
                "access_type": duel.access_type,
                "total_rounds": duel.total_rounds,
                "entrypoint": "best_of_series_next_game",
                "source_challenge_id": str(challenge_id),
                "series_id": str(duel.series_id),
                "series_game_number": duel.series_game_number,
                "series_best_of": duel.series_best_of,
                "expires_at": duel.expires_at.isoformat(),
            },
        )
        await emit_analytics_event(
            session,
            event_type="friend_challenge_series_game_created",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=initiator_user_id,
            payload={
                "challenge_id": str(duel.id),
                "source_challenge_id": str(challenge_id),
                "opponent_user_id": opponent_user_id,
                "series_id": str(duel.series_id),
                "series_game_number": duel.series_game_number,
                "series_best_of": duel.series_best_of,
            },
        )
        return GameSessionService._build_friend_challenge_snapshot(duel)

    @staticmethod
    async def join_friend_challenge_by_token(
        session: AsyncSession,
        *,
        user_id: int,
        invite_token: str,
        now_utc: datetime,
    ) -> FriendChallengeJoinResult:
        challenge = await FriendChallengesRepo.get_by_invite_token_for_update(session, invite_token)
        if challenge is None:
            raise FriendChallengeNotFoundError
        if GameSessionService._expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
            await GameSessionService._emit_friend_challenge_expired_event(
                session,
                challenge=challenge,
                happened_at=now_utc,
                source=EVENT_SOURCE_BOT,
            )
        if challenge.status == "EXPIRED":
            raise FriendChallengeExpiredError
        if challenge.status != "ACTIVE":
            raise FriendChallengeCompletedError

        if challenge.creator_user_id == user_id:
            return FriendChallengeJoinResult(
                snapshot=GameSessionService._build_friend_challenge_snapshot(challenge),
                joined_now=False,
            )

        if challenge.opponent_user_id is None:
            challenge.opponent_user_id = user_id
            challenge.updated_at = now_utc
            await emit_analytics_event(
                session,
                event_type="friend_challenge_joined",
                source=EVENT_SOURCE_BOT,
                happened_at=now_utc,
                user_id=user_id,
                payload={
                    "challenge_id": str(challenge.id),
                    "creator_user_id": challenge.creator_user_id,
                    "mode_code": challenge.mode_code,
                    "total_rounds": challenge.total_rounds,
                    "expires_at": challenge.expires_at.isoformat(),
                    "series_id": str(challenge.series_id) if challenge.series_id is not None else None,
                    "series_game_number": challenge.series_game_number,
                    "series_best_of": challenge.series_best_of,
                },
            )
            return FriendChallengeJoinResult(
                snapshot=GameSessionService._build_friend_challenge_snapshot(challenge),
                joined_now=True,
            )

        if challenge.opponent_user_id == user_id:
            return FriendChallengeJoinResult(
                snapshot=GameSessionService._build_friend_challenge_snapshot(challenge),
                joined_now=False,
            )

        raise FriendChallengeFullError

    @staticmethod
    async def start_friend_challenge_round(
        session: AsyncSession,
        *,
        user_id: int,
        challenge_id: UUID,
        idempotency_key: str,
        now_utc: datetime,
    ) -> FriendChallengeRoundStartResult:
        challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
        if challenge is None:
            raise FriendChallengeNotFoundError
        if GameSessionService._expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
            await GameSessionService._emit_friend_challenge_expired_event(
                session,
                challenge=challenge,
                happened_at=now_utc,
                source=EVENT_SOURCE_BOT,
            )
        if challenge.status == "EXPIRED":
            raise FriendChallengeExpiredError
        if challenge.status != "ACTIVE":
            raise FriendChallengeCompletedError
        if user_id not in {challenge.creator_user_id, challenge.opponent_user_id}:
            raise FriendChallengeAccessError

        participant_answered_round = (
            challenge.creator_answered_round
            if user_id == challenge.creator_user_id
            else challenge.opponent_answered_round
        )
        next_round = participant_answered_round + 1
        if next_round > challenge.total_rounds:
            return FriendChallengeRoundStartResult(
                snapshot=GameSessionService._build_friend_challenge_snapshot(challenge),
                start_result=None,
                waiting_for_opponent=challenge.status == "ACTIVE",
                already_answered_current_round=True,
            )

        existing_round_session = await QuizSessionsRepo.get_by_friend_challenge_round_user(
            session,
            friend_challenge_id=challenge.id,
            friend_challenge_round=next_round,
            user_id=user_id,
        )
        if existing_round_session is not None:
            start_result = await GameSessionService._build_start_result_from_existing_session(
                session,
                existing=existing_round_session,
                idempotent_replay=True,
            )
            return FriendChallengeRoundStartResult(
                snapshot=GameSessionService._build_friend_challenge_snapshot(challenge),
                start_result=start_result,
                waiting_for_opponent=challenge.opponent_user_id is None,
                already_answered_current_round=False,
            )

        shared_round_session = await QuizSessionsRepo.get_by_friend_challenge_round_any_user(
            session,
            friend_challenge_id=challenge.id,
            friend_challenge_round=next_round,
        )
        selection_seed = f"friend:{challenge.id}:{next_round}:{challenge.mode_code}"
        preferred_level = GameSessionService._friend_challenge_level_for_round(round_number=next_round)
        forced_question_id: str | None = (
            shared_round_session.question_id if shared_round_session is not None else None
        )
        if forced_question_id is None:
            previous_round_question_ids = await QuizSessionsRepo.list_friend_challenge_question_ids_before_round(
                session,
                friend_challenge_id=challenge.id,
                before_round=next_round,
            )
            selected_question = await select_friend_challenge_question(
                session,
                challenge.mode_code,
                local_date_berlin=berlin_local_date(now_utc),
                previous_round_question_ids=previous_round_question_ids,
                selection_seed=selection_seed,
                preferred_level=preferred_level,
            )
            forced_question_id = selected_question.question_id

        start_result = await GameSessionService.start_session(
            session,
            user_id=user_id,
            mode_code=challenge.mode_code,
            source="FRIEND_CHALLENGE",
            idempotency_key=idempotency_key,
            now_utc=now_utc,
            selection_seed_override=selection_seed,
            preferred_question_level=preferred_level,
            forced_question_id=forced_question_id,
            friend_challenge_id=challenge.id,
            friend_challenge_round=next_round,
            friend_challenge_total_rounds=challenge.total_rounds,
        )
        return FriendChallengeRoundStartResult(
            snapshot=GameSessionService._build_friend_challenge_snapshot(challenge),
            start_result=start_result,
            waiting_for_opponent=challenge.opponent_user_id is None,
            already_answered_current_round=False,
        )

    @staticmethod
    async def get_friend_challenge_snapshot_for_user(
        session: AsyncSession,
        *,
        user_id: int,
        challenge_id: UUID,
        now_utc: datetime,
    ) -> FriendChallengeSnapshot:
        challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
        if challenge is None:
            raise FriendChallengeNotFoundError
        if GameSessionService._expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
            await GameSessionService._emit_friend_challenge_expired_event(
                session,
                challenge=challenge,
                happened_at=now_utc,
                source=EVENT_SOURCE_BOT,
            )
        if user_id not in {challenge.creator_user_id, challenge.opponent_user_id}:
            raise FriendChallengeAccessError
        return GameSessionService._build_friend_challenge_snapshot(challenge)

    @staticmethod
    async def get_friend_series_score_for_user(
        session: AsyncSession,
        *,
        user_id: int,
        challenge_id: UUID,
        now_utc: datetime,
    ) -> tuple[int, int, int, int]:
        challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
        if challenge is None:
            raise FriendChallengeNotFoundError
        if GameSessionService._expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
            await GameSessionService._emit_friend_challenge_expired_event(
                session,
                challenge=challenge,
                happened_at=now_utc,
                source=EVENT_SOURCE_BOT,
            )
        if user_id not in {challenge.creator_user_id, challenge.opponent_user_id}:
            raise FriendChallengeAccessError
        if challenge.series_id is None or challenge.series_best_of <= 1:
            return (0, 0, 1, 1)

        series_challenges = await FriendChallengesRepo.list_by_series_id_for_update(
            session,
            series_id=challenge.series_id,
        )
        creator_wins, opponent_wins = GameSessionService._count_series_wins(
            series_challenges=series_challenges,
            creator_user_id=challenge.creator_user_id,
            opponent_user_id=challenge.opponent_user_id,
        )
        if user_id == challenge.creator_user_id:
            return (
                creator_wins,
                opponent_wins,
                challenge.series_game_number,
                challenge.series_best_of,
            )
        return (
            opponent_wins,
            creator_wins,
            challenge.series_game_number,
            challenge.series_best_of,
        )

    @staticmethod
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
    ) -> StartSessionResult:
        if source == "FRIEND_CHALLENGE" and (friend_challenge_id is None or friend_challenge_round is None):
            raise FriendChallengeAccessError

        existing = await QuizSessionsRepo.get_by_idempotency_key(session, idempotency_key)
        local_date = berlin_local_date(now_utc)
        if existing is not None:
            return await GameSessionService._build_start_result_from_existing_session(
                session,
                existing=existing,
                idempotent_replay=True,
            )

        if source == "DAILY_CHALLENGE":
            already_played = await QuizSessionsRepo.has_daily_challenge_on_date(
                session,
                user_id=user_id,
                local_date_berlin=local_date,
            )
            if already_played:
                raise DailyChallengeAlreadyPlayedError

        premium_active = await EntitlementsRepo.has_active_premium(session, user_id, now_utc)
        has_mode_access = await ModeAccessRepo.has_active_access(
            session,
            user_id=user_id,
            mode_code=mode_code,
            now_utc=now_utc,
        )
        if not is_mode_allowed(
            mode_code=mode_code,
            premium_active=premium_active,
            has_mode_access=has_mode_access,
        ):
            raise ModeLockedError

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
        if forced_question_id is not None:
            question = await get_question_by_id(
                session,
                mode_code,
                question_id=forced_question_id,
                local_date_berlin=local_date,
            )

        if question is None:
            effective_preferred_level = preferred_question_level
            if GameSessionService._is_persistent_adaptive_mode(mode_code=mode_code):
                mode_progress = None
                if effective_preferred_level is None:
                    mode_progress = await ModeProgressRepo.get_by_user_mode(
                        session,
                        user_id=user_id,
                        mode_code=mode_code,
                    )
                    if mode_progress is not None:
                        effective_preferred_level = mode_progress.preferred_level
                    else:
                        # Backfill for existing users: infer last reached level from history.
                        effective_preferred_level = await GameSessionService._infer_preferred_level_from_recent_attempt(
                            session,
                            user_id=user_id,
                            mode_code=mode_code,
                        )

                if mode_progress is None and effective_preferred_level is not None:
                    seeded_level = GameSessionService._clamp_level_for_mode(
                        mode_code=mode_code,
                        level=effective_preferred_level,
                    )
                    if seeded_level is not None:
                        await ModeProgressRepo.upsert_preferred_level(
                            session,
                            user_id=user_id,
                            mode_code=mode_code,
                            preferred_level=seeded_level,
                            now_utc=now_utc,
                        )
                        effective_preferred_level = seeded_level
                effective_preferred_level = GameSessionService._clamp_level_for_mode(
                    mode_code=mode_code,
                    level=effective_preferred_level,
                )

            recent_question_ids = ()
            if source != "FRIEND_CHALLENGE":
                recent_question_ids = await QuizAttemptsRepo.get_recent_question_ids_for_mode(
                    session,
                    user_id=user_id,
                    mode_code=mode_code,
                    limit=20,
                )
            selection_seed = selection_seed_override or idempotency_key
            question = await select_question_for_mode(
                session,
                mode_code,
                local_date_berlin=local_date,
                recent_question_ids=recent_question_ids,
                selection_seed=selection_seed,
                preferred_level=effective_preferred_level,
            )

        try:
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
                    started_at=now_utc,
                    local_date_berlin=local_date,
                    idempotency_key=idempotency_key,
                ),
            )
        except IntegrityError as exc:
            if source == "DAILY_CHALLENGE":
                raise DailyChallengeAlreadyPlayedError from exc
            raise

        return StartSessionResult(
            session=SessionQuestionView(
                session_id=created.id,
                question_id=question.question_id,
                text=question.text,
                options=question.options,
                mode_code=mode_code,
                source=source,
                category=question.category,
                question_number=friend_challenge_round if source == "FRIEND_CHALLENGE" else 1,
                total_questions=friend_challenge_total_rounds if source == "FRIEND_CHALLENGE" else 1,
            ),
            energy_free=energy_free,
            energy_paid=energy_paid,
            idempotent_replay=False,
        )

    @staticmethod
    async def submit_answer(
        session: AsyncSession,
        *,
        user_id: int,
        session_id: UUID,
        selected_option: int,
        idempotency_key: str,
        now_utc: datetime,
    ) -> AnswerSessionResult:
        if selected_option < 0 or selected_option > 3:
            raise InvalidAnswerOptionError

        existing_attempt = await QuizAttemptsRepo.get_by_idempotency_key(session, idempotency_key)
        if existing_attempt is not None:
            streak_snapshot = await StreakService.sync_rollover(session, user_id=user_id, now_utc=now_utc)
            replay_session = await QuizSessionsRepo.get_by_id(session, existing_attempt.session_id)
            friend_snapshot = None
            waiting_for_opponent = False
            if replay_session is not None and replay_session.friend_challenge_id is not None:
                challenge = await FriendChallengesRepo.get_by_id(session, replay_session.friend_challenge_id)
                if challenge is not None:
                    friend_snapshot = GameSessionService._build_friend_challenge_snapshot(challenge)
                    waiting_for_opponent = challenge.status == "ACTIVE"
            return AnswerSessionResult(
                session_id=existing_attempt.session_id,
                question_id=existing_attempt.question_id,
                is_correct=existing_attempt.is_correct,
                current_streak=streak_snapshot.current_streak,
                best_streak=streak_snapshot.best_streak,
                idempotent_replay=True,
                mode_code=replay_session.mode_code if replay_session is not None else None,
                source=replay_session.source if replay_session is not None else None,
                selected_answer_text=None,
                correct_answer_text=None,
                question_level=None,
                next_preferred_level=None,
                friend_challenge=friend_snapshot,
                friend_challenge_answered_round=(
                    replay_session.friend_challenge_round
                    if replay_session is not None
                    else None
                ),
                friend_challenge_round_completed=False,
                friend_challenge_waiting_for_opponent=waiting_for_opponent,
            )

        quiz_session = await QuizSessionsRepo.get_by_id_for_update(session, session_id)
        if quiz_session is None or quiz_session.user_id != user_id:
            raise SessionNotFoundError

        question = await GameSessionService._load_question_for_session(session, quiz_session=quiz_session)
        is_correct = selected_option == question.correct_option

        await QuizAttemptsRepo.create(
            session,
            attempt=QuizAttempt(
                session_id=quiz_session.id,
                user_id=user_id,
                question_id=question.question_id,
                is_correct=is_correct,
                answered_at=now_utc,
                response_ms=0,
                idempotency_key=idempotency_key,
            ),
        )

        quiz_session.status = "COMPLETED"
        quiz_session.completed_at = now_utc

        friend_snapshot = None
        friend_round_completed = False
        friend_waiting_for_opponent = False
        if quiz_session.source == "FRIEND_CHALLENGE" and quiz_session.friend_challenge_id is not None:
            challenge = await FriendChallengesRepo.get_by_id_for_update(session, quiz_session.friend_challenge_id)
            if challenge is None:
                raise FriendChallengeNotFoundError

            is_creator = challenge.creator_user_id == user_id
            if not is_creator and challenge.opponent_user_id != user_id:
                raise FriendChallengeAccessError

            answered_round = quiz_session.friend_challenge_round or 1
            expired_now = GameSessionService._expire_friend_challenge_if_due(
                challenge=challenge,
                now_utc=now_utc,
            )
            if expired_now:
                await GameSessionService._emit_friend_challenge_expired_event(
                    session,
                    challenge=challenge,
                    happened_at=now_utc,
                    source=EVENT_SOURCE_BOT,
                )

            if challenge.status == "ACTIVE":
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
                    challenge.opponent_user_id is not None
                    and challenge.creator_answered_round >= answered_round
                    and challenge.opponent_answered_round >= answered_round
                )
                if both_answered_round and challenge.status == "ACTIVE":
                    friend_round_completed = True

                max_answered_round = max(
                    challenge.creator_answered_round,
                    challenge.opponent_answered_round,
                )
                challenge.current_round = min(challenge.total_rounds, max_answered_round + 1)

                if (
                    challenge.status == "ACTIVE"
                    and challenge.opponent_user_id is not None
                    and challenge.creator_answered_round >= challenge.total_rounds
                    and challenge.opponent_answered_round >= challenge.total_rounds
                ):
                    friend_round_completed = True
                    challenge.current_round = challenge.total_rounds
                    challenge.status = "COMPLETED"
                    challenge.completed_at = now_utc
                    if challenge.creator_score > challenge.opponent_score:
                        challenge.winner_user_id = challenge.creator_user_id
                    elif challenge.opponent_score > challenge.creator_score:
                        challenge.winner_user_id = challenge.opponent_user_id
                    else:
                        challenge.winner_user_id = None

                if challenge.status == "COMPLETED" and challenge.current_round >= challenge.total_rounds:
                    if challenge.creator_score > challenge.opponent_score:
                        challenge.winner_user_id = challenge.creator_user_id
                    elif (
                        challenge.opponent_score > challenge.creator_score
                        and challenge.opponent_user_id is not None
                    ):
                        challenge.winner_user_id = challenge.opponent_user_id
                    else:
                        challenge.winner_user_id = None

            challenge.updated_at = now_utc
            friend_snapshot = GameSessionService._build_friend_challenge_snapshot(challenge)
            friend_waiting_for_opponent = challenge.status == "ACTIVE" and (
                challenge.opponent_user_id is None
                or (
                    challenge.opponent_answered_round < answered_round
                    if is_creator
                    else challenge.creator_answered_round < answered_round
                )
            )
            if challenge.status == "COMPLETED" and challenge.completed_at == now_utc:
                await emit_analytics_event(
                    session,
                    event_type="friend_challenge_completed",
                    source=EVENT_SOURCE_BOT,
                    happened_at=now_utc,
                    user_id=user_id,
                    payload={
                        "challenge_id": str(challenge.id),
                        "creator_user_id": challenge.creator_user_id,
                        "opponent_user_id": challenge.opponent_user_id,
                        "creator_score": challenge.creator_score,
                        "opponent_score": challenge.opponent_score,
                        "winner_user_id": challenge.winner_user_id,
                        "total_rounds": challenge.total_rounds,
                        "expires_at": challenge.expires_at.isoformat(),
                        "series_id": str(challenge.series_id) if challenge.series_id is not None else None,
                        "series_game_number": challenge.series_game_number,
                        "series_best_of": challenge.series_best_of,
                    },
                )

        streak_result = await StreakService.record_activity(
            session,
            user_id=user_id,
            activity_at_utc=now_utc,
        )
        next_preferred_level = GameSessionService._next_preferred_level(
            question_level=question.level,
            is_correct=is_correct,
            mode_code=quiz_session.mode_code,
        )
        if (
            GameSessionService._is_persistent_adaptive_mode(mode_code=quiz_session.mode_code)
            and next_preferred_level is not None
        ):
            progress = await ModeProgressRepo.upsert_preferred_level(
                session,
                user_id=user_id,
                mode_code=quiz_session.mode_code,
                preferred_level=next_preferred_level,
                now_utc=now_utc,
            )
            next_preferred_level = progress.preferred_level

        return AnswerSessionResult(
            session_id=quiz_session.id,
            question_id=question.question_id,
            is_correct=is_correct,
            current_streak=streak_result.current_streak,
            best_streak=streak_result.best_streak,
            idempotent_replay=False,
            mode_code=quiz_session.mode_code,
            source=quiz_session.source,
            selected_answer_text=question.options[selected_option],
            correct_answer_text=question.options[question.correct_option],
            question_level=question.level,
            next_preferred_level=next_preferred_level,
            friend_challenge=friend_snapshot,
            friend_challenge_answered_round=quiz_session.friend_challenge_round,
            friend_challenge_round_completed=friend_round_completed,
            friend_challenge_waiting_for_opponent=friend_waiting_for_opponent,
        )

    @staticmethod
    async def get_session_user_id(session: AsyncSession, session_id: UUID) -> int:
        quiz_session = await QuizSessionsRepo.get_by_id(session, session_id)
        if quiz_session is None:
            raise SessionNotFoundError
        return quiz_session.user_id
