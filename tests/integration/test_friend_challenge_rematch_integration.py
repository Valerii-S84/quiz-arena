from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.db.session import SessionLocal
from app.game.questions.runtime_bank import get_question_by_id
from app.game.sessions.service import GameSessionService
from tests.integration.friend_challenge_fixtures import UTC, _create_user


@pytest.mark.asyncio
async def test_friend_challenge_rematch_creates_bound_opponent_duel() -> None:
    now_utc = datetime(2026, 2, 19, 18, 35, tzinfo=UTC)
    creator_user_id = await _create_user("fc_rematch_creator")
    opponent_user_id = await _create_user("fc_rematch_opponent")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=5,
        )
        await GameSessionService.join_friend_challenge_by_token(
            session,
            user_id=opponent_user_id,
            invite_token=challenge.invite_token,
            now_utc=now_utc,
        )
        final_answer = None
        for round_no in range(1, 6):
            creator_round = await GameSessionService.start_friend_challenge_round(
                session,
                user_id=creator_user_id,
                challenge_id=challenge.challenge_id,
                idempotency_key=f"fc:rematch:base:creator:start:{round_no}",
                now_utc=now_utc,
            )
            opponent_round = await GameSessionService.start_friend_challenge_round(
                session,
                user_id=opponent_user_id,
                challenge_id=challenge.challenge_id,
                idempotency_key=f"fc:rematch:base:opponent:start:{round_no}",
                now_utc=now_utc,
            )
            assert creator_round.start_result is not None
            assert opponent_round.start_result is not None

            creator_session = await QuizSessionsRepo.get_by_id(
                session, creator_round.start_result.session.session_id
            )
            assert creator_session is not None
            question = await get_question_by_id(
                session,
                creator_session.mode_code,
                question_id=creator_session.question_id or "",
                local_date_berlin=creator_session.local_date_berlin,
            )
            assert question is not None

            await GameSessionService.submit_answer(
                session,
                user_id=creator_user_id,
                session_id=creator_round.start_result.session.session_id,
                selected_option=question.correct_option,
                idempotency_key=f"fc:rematch:base:creator:answer:{round_no}",
                now_utc=now_utc,
            )
            final_answer = await GameSessionService.submit_answer(
                session,
                user_id=opponent_user_id,
                session_id=opponent_round.start_result.session.session_id,
                selected_option=(question.correct_option + 1) % 4,
                idempotency_key=f"fc:rematch:base:opponent:answer:{round_no}",
                now_utc=now_utc,
            )
        assert final_answer is not None
        assert final_answer.friend_challenge is not None
        assert final_answer.friend_challenge.status == "COMPLETED"

        rematch = await GameSessionService.create_friend_challenge_rematch(
            session,
            initiator_user_id=creator_user_id,
            challenge_id=challenge.challenge_id,
            now_utc=now_utc + timedelta(minutes=1),
        )
        assert rematch.creator_user_id == creator_user_id
        assert rematch.opponent_user_id == opponent_user_id
        assert rematch.total_rounds == 5

        rematch_creator_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=creator_user_id,
            challenge_id=rematch.challenge_id,
            idempotency_key="fc:rematch:new:creator:start",
            now_utc=now_utc + timedelta(minutes=2),
        )
        rematch_opponent_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=opponent_user_id,
            challenge_id=rematch.challenge_id,
            idempotency_key="fc:rematch:new:opponent:start",
            now_utc=now_utc + timedelta(minutes=2),
        )

    assert rematch_creator_round.start_result is not None
    assert rematch_opponent_round.start_result is not None
    assert (
        rematch_creator_round.start_result.session.question_id
        == rematch_opponent_round.start_result.session.question_id
    )
