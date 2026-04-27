from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.exc import DBAPIError

from app.db.session import engine

T = TypeVar("T")


def is_deadlock_detected(exc: BaseException) -> bool:
    return "deadlock detected" in str(exc).lower()


async def run_with_deadlock_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay_seconds: float = 0.2,
) -> T:
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except DBAPIError as exc:
            if not is_deadlock_detected(exc) or attempt == attempts:
                raise
            await engine.dispose()
            await asyncio.sleep(base_delay_seconds * attempt)
    raise AssertionError("deadlock retry exhausted without returning or raising")
