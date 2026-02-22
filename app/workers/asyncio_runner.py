from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

from app.db.session import dispose_engine

T = TypeVar("T")


async def _run_with_fresh_db_pool(awaitable: Awaitable[T]) -> T:
    await dispose_engine()
    try:
        return await awaitable
    finally:
        await dispose_engine()


def run_async_job(awaitable: Awaitable[T]) -> T:
    return asyncio.run(_run_with_fresh_db_pool(awaitable))
