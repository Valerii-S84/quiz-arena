from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram.exceptions import TelegramForbiddenError


@dataclass(frozen=True, slots=True)
class DailyCupNonfinishersSummaryDeliveryResult:
    sent: int
    failed: int


async def deliver_daily_cup_nonfinishers_summary(
    *,
    bot: Any,
    nonfinishers: list[int],
    telegram_targets: dict[int, int],
    text: str,
) -> DailyCupNonfinishersSummaryDeliveryResult:
    sent = 0
    failed = 0
    for user_id in nonfinishers:
        chat_id = telegram_targets.get(user_id)
        if chat_id is None:
            failed += 1
            continue
        try:
            await bot.send_message(chat_id=chat_id, text=text)
            sent += 1
        except TelegramForbiddenError:
            failed += 1
        except Exception:
            failed += 1
    return DailyCupNonfinishersSummaryDeliveryResult(sent=sent, failed=failed)


__all__ = [
    "DailyCupNonfinishersSummaryDeliveryResult",
    "deliver_daily_cup_nonfinishers_summary",
]
