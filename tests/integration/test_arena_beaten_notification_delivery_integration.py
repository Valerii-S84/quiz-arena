from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import select

from app.db.models.production_reliability import TelegramDeliveryAttempt
from app.db.session import SessionLocal
from app.game.arena_duels.constants import ARENA_BEATEN_NOTIFICATION_TYPE
from app.game.arena_duels.types import ArenaBeatenNotification
from app.services.telegram_delivery import deliver_telegram_once
from app.workers.tasks.arena_duels_notification_delivery_target import beaten_delivery_attempt


def _notification() -> ArenaBeatenNotification:
    return ArenaBeatenNotification(
        arena_duel_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        previous_best_attempt_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        previous_best_user_id=11,
        previous_best_score=6,
        previous_best_time_ms=48_000,
        new_best_attempt_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        new_best_user_id=22,
        new_best_score=7,
        new_best_time_ms=52_000,
        notification_type=ARENA_BEATEN_NOTIFICATION_TYPE,
    )


async def test_concurrent_arena_delivery_claim_sends_once() -> None:
    send_started = asyncio.Event()
    release_send = asyncio.Event()
    send_total = 0
    attempt = beaten_delivery_attempt(
        notification=_notification(),
        telegram_user_id=110_000_011,
    )

    async def _send() -> None:
        nonlocal send_total
        send_total += 1
        send_started.set()
        await release_send.wait()

    first_delivery = asyncio.create_task(
        deliver_telegram_once(
            SessionLocal,
            attempt=attempt,
            send=_send,
            allow_stale_pending_replay_send=True,
        )
    )
    await send_started.wait()
    concurrent_outcome = await deliver_telegram_once(
        SessionLocal,
        attempt=attempt,
        send=_send,
        allow_stale_pending_replay_send=True,
    )
    release_send.set()
    first_outcome = await first_delivery

    assert first_outcome.status == "SENT"
    assert concurrent_outcome.status == "RETRY"
    assert concurrent_outcome.attempted is False
    assert send_total == 1

    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(TelegramDeliveryAttempt).where(
                    TelegramDeliveryAttempt.idempotency_key == attempt.idempotency_key
                )
            )
        ).scalar_one()
    assert row.status == "SENT"
