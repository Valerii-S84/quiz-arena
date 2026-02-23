from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.db.session import SessionLocal
from app.game.questions.runtime_bank import get_question_by_id
from app.game.sessions.service import GameSessionService
from tests.integration.friend_challenge_fixtures import (
    UTC,
    _create_user,
    _seed_friend_challenge_questions,
)


@pytest.mark.asyncio
async def test_friend_challenge_default_uses_12_round_plan_with_level_mix_and_free_energy() -> None:
    now_utc = datetime(2026, 2, 19, 19, 0, tzinfo=UTC)
    await _seed_friend_challenge_questions(now_utc)
    creator_user_id = await _create_user("fc_plan_creator")
    opponent_user_id = await _create_user("fc_plan_opponent")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
        )
        await GameSessionService.join_friend_challenge_by_token(
            session,
            user_id=opponent_user_id,
            invite_token=challenge.invite_token,
            now_utc=now_utc,
        )

    levels: list[str] = []
    categories: list[str] = []
    final_answer = None

    for round_no in range(1, 13):
        async with SessionLocal.begin() as session:
            creator_round = await GameSessionService.start_friend_challenge_round(
                session,
                user_id=creator_user_id,
                challenge_id=challenge.challenge_id,
                idempotency_key=f"fc:plan:round:{round_no}:creator:start",
                now_utc=now_utc + timedelta(minutes=round_no),
            )
            opponent_round = await GameSessionService.start_friend_challenge_round(
                session,
                user_id=opponent_user_id,
                challenge_id=challenge.challenge_id,
                idempotency_key=f"fc:plan:round:{round_no}:opponent:start",
                now_utc=now_utc + timedelta(minutes=round_no),
            )

            assert creator_round.start_result is not None
            assert opponent_round.start_result is not None
            assert (
                creator_round.start_result.session.question_id
                == opponent_round.start_result.session.question_id
            )

            creator_session = await QuizSessionsRepo.get_by_id(
                session, creator_round.start_result.session.session_id
            )
            assert creator_session is not None
            assert creator_session.energy_cost_total == 0

            question = await get_question_by_id(
                session,
                creator_session.mode_code,
                question_id=creator_session.question_id or "",
                local_date_berlin=creator_session.local_date_berlin,
            )
            assert question is not None
            levels.append((question.level or "").upper())
            categories.append(question.category or "")

            await GameSessionService.submit_answer(
                session,
                user_id=creator_user_id,
                session_id=creator_round.start_result.session.session_id,
                selected_option=question.correct_option,
                idempotency_key=f"fc:plan:round:{round_no}:creator:answer",
                now_utc=now_utc + timedelta(minutes=round_no),
            )
            final_answer = await GameSessionService.submit_answer(
                session,
                user_id=opponent_user_id,
                session_id=opponent_round.start_result.session.session_id,
                selected_option=(question.correct_option + 1) % 4,
                idempotency_key=f"fc:plan:round:{round_no}:opponent:answer",
                now_utc=now_utc + timedelta(minutes=round_no),
            )

    assert final_answer is not None
    assert final_answer.friend_challenge is not None
    assert final_answer.friend_challenge.status == "COMPLETED"
    assert len(levels) == 12
    assert levels.count("A1") == 3
    assert levels.count("A2") == 6
    assert levels.count("B1") == 3
    assert len({category for category in categories if category}) >= 3
