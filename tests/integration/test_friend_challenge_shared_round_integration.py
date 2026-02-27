from __future__ import annotations

from datetime import datetime

import pytest

from app.db.session import SessionLocal
from app.game.questions.types import QuizQuestion
from app.game.sessions.service import GameSessionService
from tests.integration.friend_challenge_fixtures import UTC, _create_user


@pytest.mark.asyncio
async def test_friend_challenge_second_player_reuses_round_question_from_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 2, 19, 18, 50, tzinfo=UTC)
    creator_user_id = await _create_user("fc_shared_round_creator")
    opponent_user_id = await _create_user("fc_shared_round_opponent")

    selection_calls = 0

    async def fake_select_friend_challenge_question(*args, **kwargs):  # noqa: ANN002, ANN003
        nonlocal selection_calls
        selection_calls += 1
        question_id = "qm_a1a2_001" if selection_calls == 1 else "qm_a1a2_002"
        return QuizQuestion(
            question_id=question_id,
            text=f"Question {question_id}",
            options=("A", "B", "C", "D"),
            correct_option=0,
            level="A1",
            category="Test",
        )

    monkeypatch.setattr(
        "app.game.sessions.service.select_friend_challenge_question",
        fake_select_friend_challenge_question,
    )

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
        creator_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=creator_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:shared:creator:start",
            now_utc=now_utc,
        )
        opponent_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=opponent_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc:shared:opponent:start",
            now_utc=now_utc,
        )

    assert creator_round.start_result is not None
    assert opponent_round.start_result is not None
    assert (
        creator_round.start_result.session.question_id
        == opponent_round.start_result.session.question_id
    )
    assert selection_calls == challenge.total_rounds
