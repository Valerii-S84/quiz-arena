from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.db.session import engine


def _standings_lock_key(tournament_id: UUID) -> str:
    return f"private-tournament-standings:{tournament_id}"


async def _invalidate_and_close(connection: AsyncConnection) -> None:
    try:
        await connection.invalidate()
    finally:
        await connection.close()


async def _unlock_connection(connection: AsyncConnection) -> None:
    result = await connection.execute(
        text("SELECT pg_advisory_unlock(hashtextextended(:lock_key, 0))"),
        {"lock_key": connection.info["standings_lock_key"]},
    )
    if result.scalar_one() is not True:
        raise RuntimeError("private tournament standings lock ownership was lost")


async def lock_standings_phase_transition(
    session: AsyncSession,
    *,
    tournament_id: UUID,
) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": _standings_lock_key(tournament_id)},
    )


async def _release_connection(
    connection: AsyncConnection,
    *,
    acquired: bool,
    discard: bool = False,
) -> None:
    try:
        if discard:
            await connection.invalidate()
        elif acquired:
            await _unlock_connection(connection)
    except BaseException:
        await _invalidate_and_close(connection)
        raise
    await connection.close()


async def _finish_release(
    connection: AsyncConnection,
    *,
    acquired: bool,
    discard: bool = False,
) -> None:
    release_task = asyncio.create_task(
        _release_connection(connection, acquired=acquired, discard=discard)
    )
    cancellation: asyncio.CancelledError | None = None
    while not release_task.done():
        try:
            await asyncio.shield(release_task)
        except asyncio.CancelledError as exc:
            cancellation = exc
    if cancellation is not None:
        raise cancellation
    release_task.result()


@asynccontextmanager
async def private_tournament_standings_mutex(
    tournament_id: UUID,
) -> AsyncIterator[None]:
    connection = await engine.connect()
    connection.info["standings_lock_key"] = _standings_lock_key(tournament_id)
    try:
        connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
        await connection.execute(
            text("SELECT pg_advisory_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": connection.info["standings_lock_key"]},
        )
    except BaseException:
        await _finish_release(connection, acquired=False, discard=True)
        raise

    active_error: BaseException | None = None
    try:
        yield
    except BaseException as exc:
        active_error = exc
        raise
    finally:
        try:
            await _finish_release(connection, acquired=True)
        except BaseException:
            if active_error is None:
                raise


__all__ = [
    "lock_standings_phase_transition",
    "private_tournament_standings_mutex",
]
