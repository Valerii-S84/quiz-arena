from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.game.sessions.service import sessions_submit
from app.game.sessions.types import AnswerSessionResult
from tests.game.friend_challenges_unit_support import NOW_UTC, Session, async_return


@pytest.mark.asyncio
async def test_submit_replays_friend_attempt_without_mutating_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay_session = SimpleNamespace(
        id=UUID("123e4567-e89b-12d3-a456-426614174001"),
        user_id=11,
        source="FRIEND_CHALLENGE",
        status="COMPLETED",
        mode_code="QUICK_MIX_A1A2",
        question_id="friend-q-1",
    )
    existing_attempt = SimpleNamespace(
        session_id=replay_session.id,
        question_id="friend-q-1",
        is_correct=True,
    )
    replay_result = AnswerSessionResult(
        session_id=existing_attempt.session_id,
        question_id="friend-q-1",
        is_correct=True,
        current_streak=3,
        best_streak=5,
        idempotent_replay=True,
        mode_code="QUICK_MIX_A1A2",
        source="FRIEND_CHALLENGE",
    )

    async def _unexpected_friend_challenge_mutation(*_args, **_kwargs):
        pytest.fail("replayed submits must not mutate friend challenge state")

    monkeypatch.setattr(
        sessions_submit.QuizSessionsRepo,
        "get_by_id_for_update",
        async_return(replay_session),
    )
    monkeypatch.setattr(
        sessions_submit.QuizAttemptsRepo,
        "get_latest_for_session",
        async_return(existing_attempt),
    )
    monkeypatch.setattr(sessions_submit, "build_replay_answer_result", async_return(replay_result))
    monkeypatch.setattr(
        sessions_submit,
        "_apply_friend_challenge_answer",
        _unexpected_friend_challenge_mutation,
    )

    result = await sessions_submit.submit_answer(
        Session(),
        user_id=11,
        session_id=uuid4(),
        selected_option=1,
        idempotency_key="friend-answer:duplicate",
        now_utc=NOW_UTC,
    )

    assert result is replay_result
