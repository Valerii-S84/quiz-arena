from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.bot.texts.de import TEXTS_DE
from app.services.telegram_delivery import (
    TelegramDeliveryTarget,
    build_delivery_idempotency_key,
    hash_chat_id,
)


@dataclass(frozen=True)
class DailyCupCancelDeliveryOperations:
    default_bot_factory: Callable[[], Any]
    now_utc: Callable[[], datetime]
    prepare_delivery: Callable[..., Any]
    begin_dispatch: Callable[..., Any]
    mark_failed: Callable[..., Any]
    mark_sent: Callable[..., Any]
    target_factory: Callable[..., TelegramDeliveryTarget]


async def send_daily_cup_canceled_messages(
    *,
    telegram_targets: list[int],
    tournament_id: str | None,
    bot_factory: Callable[[], Any] | None,
    operations: DailyCupCancelDeliveryOperations,
) -> None:
    if not telegram_targets:
        return
    resolved_bot_factory = (
        bot_factory if bot_factory is not None else operations.default_bot_factory
    )
    bot = resolved_bot_factory()
    happened_at = operations.now_utc()
    correlation_id = tournament_id or "unknown"
    try:
        for chat_id in telegram_targets:
            target = operations.target_factory(
                correlation_id=correlation_id,
                chat_id=chat_id,
            )
            delivery = await operations.prepare_delivery(
                target=target,
                happened_at=happened_at,
            )
            if not delivery.should_send:
                continue
            await operations.begin_dispatch(delivery, happened_at=happened_at)
            try:
                await bot.send_message(chat_id=chat_id, text=TEXTS_DE["msg.daily_cup.canceled"])
            except Exception as exc:
                await operations.mark_failed(
                    idempotency_key=target.idempotency_key,
                    happened_at=happened_at,
                    exc=exc,
                )
                continue
            await operations.mark_sent(
                idempotency_key=target.idempotency_key,
                happened_at=happened_at,
            )
    finally:
        await bot.session.close()


def daily_cup_cancel_delivery_target(
    *,
    correlation_id: str,
    chat_id: int,
) -> TelegramDeliveryTarget:
    content_version = "status:canceled"
    target_id = f"{hash_chat_id(chat_id)}:{content_version}"
    return TelegramDeliveryTarget(
        flow="daily_cup_cancel_message",
        task_name="daily_cup.close_registration_and_start",
        correlation_id=correlation_id,
        target_type="chat_hash",
        target_id=target_id,
        idempotency_key=build_delivery_idempotency_key(
            flow="daily_cup_cancel_message",
            correlation_id=correlation_id,
            target_type="chat_hash",
            target_id=target_id,
        ),
        telegram_user_id=chat_id,
        chat_id=chat_id,
        safe_context={
            "tournament_id": correlation_id,
            "content_version": content_version,
            "pending_replay_safe": False,
        },
    )
