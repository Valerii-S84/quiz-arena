from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.bot.handlers.gameplay_flows import friend_answer_flow
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.questions.runtime_bank import get_question_by_id
from app.game.sessions.service import GameSessionService
from tests.bot.helpers import DummyCallback, DummyMessage
from tests.integration.friend_challenge_fixtures import UTC, _create_user


async def _telegram_user_id(user_id: int) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.get_by_id(session, user_id)
    assert user is not None
    return int(user.telegram_user_id)


async def _submit_friend_round_answer(
    *,
    user_id: int,
    challenge_id,
    round_no: int,
    now_utc: datetime,
    correct: bool,
):
    async with SessionLocal.begin() as session:
        round_start = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=user_id,
            challenge_id=challenge_id,
            idempotency_key=f"fc:push:start:{user_id}:{round_no}",
            now_utc=now_utc,
        )
        assert round_start.start_result is not None
        quiz_session = await QuizSessionsRepo.get_by_id(
            session, round_start.start_result.session.session_id
        )
        assert quiz_session is not None
        question = await get_question_by_id(
            session,
            quiz_session.mode_code,
            question_id=quiz_session.question_id or "",
            local_date_berlin=quiz_session.local_date_berlin,
        )
        assert question is not None
        selected_option = question.correct_option if correct else (question.correct_option + 1) % 4
        return await GameSessionService.submit_answer(
            session,
            user_id=user_id,
            session_id=round_start.start_result.session.session_id,
            selected_option=selected_option,
            idempotency_key=f"fc:push:answer:{user_id}:{round_no}",
            now_utc=now_utc,
        )


async def _run_friend_answer_branch(
    *,
    actor_user_id: int,
    actor_telegram_user_id: int,
    result,
) -> list[tuple[int, str, str | None]]:
    notifications: list[tuple[int, str, str | None]] = []

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=actor_user_id, free_energy=20, paid_energy=0)

    async def _fake_resolve_label(**kwargs):
        del kwargs
        return "Freund"

    async def _fake_notify(callback, *, opponent_user_id, text, reply_markup=None):
        del callback
        callback_data = None
        if reply_markup is not None:
            callback_data = reply_markup.inline_keyboard[0][0].callback_data
        notifications.append((opponent_user_id, text, callback_data))

    async def _fake_send_question(*args, **kwargs):
        del args, kwargs
        return None

    callback = DummyCallback(
        data="answer:test:0",
        from_user=SimpleNamespace(
            id=actor_telegram_user_id,
            username=None,
            first_name="Friend",
            language_code="de",
        ),
        message=DummyMessage(),
    )
    await friend_answer_flow.handle_friend_answer_branch(
        callback,
        result=result,
        now_utc=datetime(2026, 2, 19, 19, 0, tzinfo=UTC),
        session_local=SessionLocal,
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_home_snapshot),
        game_session_service=GameSessionService,
        resolve_opponent_label=_fake_resolve_label,
        notify_opponent=_fake_notify,
        friend_opponent_user_id=lambda challenge, user_id: (
            challenge.opponent_user_id
            if challenge.creator_user_id == user_id
            else challenge.creator_user_id
        ),
        build_friend_score_text=lambda **kwargs: "score",
        build_friend_ttl_text=lambda **kwargs: None,
        build_friend_finish_text=lambda **kwargs: "finish",
        build_public_badge_label=lambda **kwargs: "badge",
        build_friend_proof_card_text=lambda **kwargs: "proof",
        enqueue_friend_challenge_proof_cards=lambda **kwargs: None,
        build_series_progress_text=lambda **kwargs: "series",
        send_friend_round_question=_fake_send_question,
    )
    return notifications


async def _create_joined_duel(now_utc: datetime) -> tuple[int, int, object]:
    creator_user_id = await _create_user(f"fc_push_creator_{now_utc.timestamp()}")
    opponent_user_id = await _create_user(f"fc_push_opponent_{now_utc.timestamp()}")
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
    return creator_user_id, opponent_user_id, challenge.challenge_id


@pytest.mark.asyncio
async def test_friend_challenge_opponent_round_one_does_not_send_push() -> None:
    now_utc = datetime(2026, 2, 19, 19, 0, tzinfo=UTC)
    _creator_user_id, opponent_user_id, challenge_id = await _create_joined_duel(now_utc)
    opponent_telegram_user_id = await _telegram_user_id(opponent_user_id)

    result = await _submit_friend_round_answer(
        user_id=opponent_user_id,
        challenge_id=challenge_id,
        round_no=1,
        now_utc=now_utc,
        correct=True,
    )

    notifications = await _run_friend_answer_branch(
        actor_user_id=opponent_user_id,
        actor_telegram_user_id=opponent_telegram_user_id,
        result=result,
    )

    assert notifications == []


@pytest.mark.asyncio
async def test_friend_challenge_opponent_round_three_does_not_send_push() -> None:
    now_utc = datetime(2026, 2, 19, 19, 15, tzinfo=UTC)
    _creator_user_id, opponent_user_id, challenge_id = await _create_joined_duel(now_utc)
    opponent_telegram_user_id = await _telegram_user_id(opponent_user_id)

    for round_no in range(1, 4):
        result = await _submit_friend_round_answer(
            user_id=opponent_user_id,
            challenge_id=challenge_id,
            round_no=round_no,
            now_utc=now_utc,
            correct=True,
        )

    notifications = await _run_friend_answer_branch(
        actor_user_id=opponent_user_id,
        actor_telegram_user_id=opponent_telegram_user_id,
        result=result,
    )

    assert notifications == []


@pytest.mark.asyncio
async def test_friend_challenge_opponent_finish_sends_exactly_one_push_if_creator_not_started() -> (
    None
):
    now_utc = datetime(2026, 2, 19, 19, 30, tzinfo=UTC)
    creator_user_id, opponent_user_id, challenge_id = await _create_joined_duel(now_utc)
    opponent_telegram_user_id = await _telegram_user_id(opponent_user_id)

    notifications: list[tuple[int, str, str | None]] = []
    for round_no in range(1, 6):
        result = await _submit_friend_round_answer(
            user_id=opponent_user_id,
            challenge_id=challenge_id,
            round_no=round_no,
            now_utc=now_utc,
            correct=True,
        )
        notifications.extend(
            await _run_friend_answer_branch(
                actor_user_id=opponent_user_id,
                actor_telegram_user_id=opponent_telegram_user_id,
                result=result,
            )
        )

    assert notifications == [
        (
            creator_user_id,
            "Dein Freund hat gespielt – du bist dran!",
            f"friend:next:{challenge_id}",
        )
    ]


@pytest.mark.asyncio
async def test_friend_challenge_opponent_finish_skips_push_if_creator_already_started() -> None:
    now_utc = datetime(2026, 2, 19, 19, 45, tzinfo=UTC)
    creator_user_id, opponent_user_id, challenge_id = await _create_joined_duel(now_utc)
    opponent_telegram_user_id = await _telegram_user_id(opponent_user_id)

    await _submit_friend_round_answer(
        user_id=creator_user_id,
        challenge_id=challenge_id,
        round_no=1,
        now_utc=now_utc,
        correct=True,
    )

    notifications: list[tuple[int, str, str | None]] = []
    for round_no in range(1, 6):
        result = await _submit_friend_round_answer(
            user_id=opponent_user_id,
            challenge_id=challenge_id,
            round_no=round_no,
            now_utc=now_utc,
            correct=True,
        )
        notifications.extend(
            await _run_friend_answer_branch(
                actor_user_id=opponent_user_id,
                actor_telegram_user_id=opponent_telegram_user_id,
                result=result,
            )
        )

    assert notifications == []
