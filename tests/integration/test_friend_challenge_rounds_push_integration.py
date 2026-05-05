from __future__ import annotations

from datetime import datetime

import pytest

from tests.integration.friend_challenge_fixtures import UTC
from tests.integration.friend_challenge_push_harness import (
    create_joined_duel,
    run_friend_answer_branch,
    submit_friend_round_answer,
    telegram_user_id,
)


@pytest.mark.asyncio
async def test_friend_challenge_opponent_round_one_does_not_send_push() -> None:
    now_utc = datetime(2026, 2, 19, 19, 0, tzinfo=UTC)
    _creator_user_id, opponent_user_id, challenge_id = await create_joined_duel(now_utc)
    opponent_telegram_user_id = await telegram_user_id(opponent_user_id)

    result = await submit_friend_round_answer(
        user_id=opponent_user_id,
        challenge_id=challenge_id,
        round_no=1,
        now_utc=now_utc,
        correct=True,
    )
    notifications = await run_friend_answer_branch(
        actor_user_id=opponent_user_id,
        actor_telegram_user_id=opponent_telegram_user_id,
        result=result,
    )

    assert notifications == []


@pytest.mark.asyncio
async def test_friend_challenge_opponent_round_three_does_not_send_push() -> None:
    now_utc = datetime(2026, 2, 19, 19, 15, tzinfo=UTC)
    _creator_user_id, opponent_user_id, challenge_id = await create_joined_duel(now_utc)
    opponent_telegram_user_id = await telegram_user_id(opponent_user_id)

    for round_no in range(1, 4):
        result = await submit_friend_round_answer(
            user_id=opponent_user_id,
            challenge_id=challenge_id,
            round_no=round_no,
            now_utc=now_utc,
            correct=True,
        )
    notifications = await run_friend_answer_branch(
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
    creator_user_id, opponent_user_id, challenge_id = await create_joined_duel(now_utc)
    opponent_telegram_user_id = await telegram_user_id(opponent_user_id)

    notifications: list[tuple[int, str, str | None]] = []
    for round_no in range(1, 8):
        result = await submit_friend_round_answer(
            user_id=opponent_user_id,
            challenge_id=challenge_id,
            round_no=round_no,
            now_utc=now_utc,
            correct=True,
        )
        notifications.extend(
            await run_friend_answer_branch(
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
    creator_user_id, opponent_user_id, challenge_id = await create_joined_duel(now_utc)
    opponent_telegram_user_id = await telegram_user_id(opponent_user_id)

    await submit_friend_round_answer(
        user_id=creator_user_id,
        challenge_id=challenge_id,
        round_no=1,
        now_utc=now_utc,
        correct=True,
    )

    notifications: list[tuple[int, str, str | None]] = []
    for round_no in range(1, 8):
        result = await submit_friend_round_answer(
            user_id=opponent_user_id,
            challenge_id=challenge_id,
            round_no=round_no,
            now_utc=now_utc,
            correct=True,
        )
        notifications.extend(
            await run_friend_answer_branch(
                actor_user_id=opponent_user_id,
                actor_telegram_user_id=opponent_telegram_user_id,
                result=result,
            )
        )

    assert notifications == []
