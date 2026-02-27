from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.economy.streak.service import StreakService
from app.game.friend_challenges.constants import is_duel_playable_status, normalize_duel_status
from app.game.sessions.types import AnswerSessionResult

from .friend_challenges_internal import _build_friend_challenge_snapshot
from .sessions_submit_daily import build_daily_replay_state


async def build_replay_answer_result(
    session: AsyncSession,
    *,
    user_id: int,
    replay_session: QuizSession | None,
    replay_attempt: QuizAttempt | None,
    now_utc: datetime,
) -> AnswerSessionResult:
    streak_snapshot = await StreakService.sync_rollover(
        session,
        user_id=user_id,
        now_utc=now_utc,
    )
    friend_snapshot = None
    waiting_for_opponent = False
    if replay_session is not None and replay_session.friend_challenge_id is not None:
        challenge = await FriendChallengesRepo.get_by_id(
            session, replay_session.friend_challenge_id
        )
        if challenge is not None:
            challenge.status = normalize_duel_status(
                status=challenge.status,
                has_opponent=challenge.opponent_user_id is not None,
            )
            friend_snapshot = _build_friend_challenge_snapshot(challenge)
            waiting_for_opponent = is_duel_playable_status(challenge.status)

    daily_state = None
    if replay_session is not None and replay_session.source == "DAILY_CHALLENGE":
        daily_state = await build_daily_replay_state(
            session,
            replay_session=replay_session,
            current_streak=streak_snapshot.current_streak,
            best_streak=streak_snapshot.best_streak,
        )

    return AnswerSessionResult(
        session_id=(
            replay_attempt.session_id
            if replay_attempt is not None
            else replay_session.id if replay_session is not None else UUID(int=0)
        ),
        question_id=(
            replay_attempt.question_id
            if replay_attempt is not None
            else (replay_session.question_id or "") if replay_session is not None else ""
        ),
        is_correct=(replay_attempt.is_correct if replay_attempt is not None else False),
        current_streak=(
            daily_state.current_streak
            if daily_state is not None
            else streak_snapshot.current_streak
        ),
        best_streak=(
            daily_state.best_streak if daily_state is not None else streak_snapshot.best_streak
        ),
        idempotent_replay=True,
        mode_code=(replay_session.mode_code if replay_session is not None else None),
        source=(replay_session.source if replay_session is not None else None),
        selected_answer_text=None,
        correct_answer_text=None,
        question_level=None,
        next_preferred_level=None,
        friend_challenge=friend_snapshot,
        friend_challenge_answered_round=(
            replay_session.friend_challenge_round if replay_session is not None else None
        ),
        friend_challenge_round_completed=False,
        friend_challenge_waiting_for_opponent=waiting_for_opponent,
        daily_run_id=(daily_state.daily_run_id if daily_state is not None else None),
        daily_current_question=(daily_state.current_question if daily_state is not None else None),
        daily_total_questions=(daily_state.total_questions if daily_state is not None else None),
        daily_score=(daily_state.score if daily_state is not None else None),
        daily_completed=(daily_state.completed if daily_state is not None else False),
    )
