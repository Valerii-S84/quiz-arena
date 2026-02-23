from __future__ import annotations

from datetime import datetime

import pytest

from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.db.session import SessionLocal
from app.game.questions.runtime_bank import get_question_by_id
from app.game.sessions.service import GameSessionService
from tests.integration.friend_challenge_fixtures import UTC, _create_user


@pytest.mark.asyncio
async def test_friend_challenge_uses_same_question_for_both_users_and_updates_round_score() -> None:
    now_utc = datetime(2026, 2, 19, 18, 0, tzinfo=UTC)
    creator_user_id = await _create_user("fc_sameq_creator")
    opponent_user_id = await _create_user("fc_sameq_opponent")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=3,
        )
        await GameSessionService.join_friend_challenge_by_token(
            session,
            user_id=opponent_user_id,
            invite_token=challenge.invite_token,
            now_utc=now_utc,
        )
        creator_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=creator_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:round1:creator:start",
            now_utc=now_utc,
        )
        opponent_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=opponent_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:round1:opponent:start",
            now_utc=now_utc,
        )

    assert creator_round.start_result is not None
    assert opponent_round.start_result is not None
    assert (
        creator_round.start_result.session.question_id
        == opponent_round.start_result.session.question_id
    )

    creator_session_id = creator_round.start_result.session.session_id
    opponent_session_id = opponent_round.start_result.session.session_id

    async with SessionLocal.begin() as session:
        creator_session = await QuizSessionsRepo.get_by_id(session, creator_session_id)
        assert creator_session is not None
        question = await get_question_by_id(
            session,
            creator_session.mode_code,
            question_id=creator_session.question_id or "",
            local_date_berlin=creator_session.local_date_berlin,
        )
        assert question is not None
        correct_option = question.correct_option

        first_answer = await GameSessionService.submit_answer(
            session,
            user_id=creator_user_id,
            session_id=creator_session_id,
            selected_option=correct_option,
            idempotency_key="fc:round1:creator:answer",
            now_utc=now_utc,
        )
        second_answer = await GameSessionService.submit_answer(
            session,
            user_id=opponent_user_id,
            session_id=opponent_session_id,
            selected_option=(correct_option + 1) % 4,
            idempotency_key="fc:round1:opponent:answer",
            now_utc=now_utc,
        )

    assert first_answer.friend_challenge is not None
    assert first_answer.friend_challenge_round_completed is False
    assert first_answer.friend_challenge_waiting_for_opponent is True

    assert second_answer.friend_challenge is not None
    assert second_answer.friend_challenge_round_completed is True
    assert second_answer.friend_challenge.status == "ACTIVE"
    assert second_answer.friend_challenge.current_round == 2
    assert second_answer.friend_challenge.creator_score == 1
    assert second_answer.friend_challenge.opponent_score == 0


@pytest.mark.asyncio
async def test_friend_challenge_completes_and_sets_winner() -> None:
    now_utc = datetime(2026, 2, 19, 18, 30, tzinfo=UTC)
    creator_user_id = await _create_user("fc_done_creator")
    opponent_user_id = await _create_user("fc_done_opponent")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=1,
        )
        await GameSessionService.join_friend_challenge_by_token(
            session,
            user_id=opponent_user_id,
            invite_token=challenge.invite_token,
            now_utc=now_utc,
        )
        creator_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=creator_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:done:creator:start",
            now_utc=now_utc,
        )
        opponent_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=opponent_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:done:opponent:start",
            now_utc=now_utc,
        )

    assert creator_round.start_result is not None
    assert opponent_round.start_result is not None

    creator_session_id = creator_round.start_result.session.session_id
    opponent_session_id = opponent_round.start_result.session.session_id

    async with SessionLocal.begin() as session:
        creator_session = await QuizSessionsRepo.get_by_id(session, creator_session_id)
        assert creator_session is not None
        question = await get_question_by_id(
            session,
            creator_session.mode_code,
            question_id=creator_session.question_id or "",
            local_date_berlin=creator_session.local_date_berlin,
        )
        assert question is not None
        correct_option = question.correct_option

        await GameSessionService.submit_answer(
            session,
            user_id=creator_user_id,
            session_id=creator_session_id,
            selected_option=(correct_option + 1) % 4,
            idempotency_key="fc:done:creator:answer",
            now_utc=now_utc,
        )
        final_answer = await GameSessionService.submit_answer(
            session,
            user_id=opponent_user_id,
            session_id=opponent_session_id,
            selected_option=correct_option,
            idempotency_key="fc:done:opponent:answer",
            now_utc=now_utc,
        )

    assert final_answer.friend_challenge is not None
    assert final_answer.friend_challenge_round_completed is True
    assert final_answer.friend_challenge.status == "COMPLETED"
    assert final_answer.friend_challenge.winner_user_id == opponent_user_id


@pytest.mark.asyncio
async def test_friend_challenge_creator_can_continue_without_waiting_for_opponent() -> None:
    now_utc = datetime(2026, 2, 19, 18, 45, tzinfo=UTC)
    creator_user_id = await _create_user("fc_async_creator")
    opponent_user_id = await _create_user("fc_async_opponent")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=3,
        )
        await GameSessionService.join_friend_challenge_by_token(
            session,
            user_id=opponent_user_id,
            invite_token=challenge.invite_token,
            now_utc=now_utc,
        )
        round_one = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=creator_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:async:creator:start:1",
            now_utc=now_utc,
        )
        assert round_one.start_result is not None

        creator_session = await QuizSessionsRepo.get_by_id(
            session, round_one.start_result.session.session_id
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
            session_id=round_one.start_result.session.session_id,
            selected_option=question.correct_option,
            idempotency_key="fc:async:creator:answer:1",
            now_utc=now_utc,
        )

        round_two = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=creator_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:async:creator:start:2",
            now_utc=now_utc,
        )

    assert round_two.start_result is not None
    assert round_two.snapshot.current_round >= 2
