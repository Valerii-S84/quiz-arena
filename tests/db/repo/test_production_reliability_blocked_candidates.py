from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.production_reliability_repo import TelegramDeliveryAttemptsRepo


class SyncExecuteSession:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    async def execute(self, statement: Any):
        return self.connection.execute(statement)


def _sqlite_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S.%f")


def _create_connection() -> tuple[Any, Connection]:
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.execute(
        text(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                last_seen_at DATETIME NULL
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE telegram_delivery_attempts (
                id INTEGER PRIMARY KEY,
                telegram_user_id INTEGER,
                status TEXT NOT NULL,
                is_blocked_candidate INTEGER NOT NULL,
                failed_at DATETIME NULL,
                updated_at DATETIME NOT NULL,
                created_at DATETIME NOT NULL
            )
            """
        )
    )
    return engine, connection


def _insert_blocked_attempt(
    connection: Connection,
    *,
    row_id: int,
    telegram_user_id: int,
    blocked_at: datetime,
    is_blocked_candidate: bool = True,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO telegram_delivery_attempts (
                id,
                telegram_user_id,
                status,
                is_blocked_candidate,
                failed_at,
                updated_at,
                created_at
            )
            VALUES (
                :id,
                :telegram_user_id,
                'FAILED',
                :is_blocked_candidate,
                :blocked_at,
                :blocked_at,
                :blocked_at
            )
            """
        ),
        {
            "id": row_id,
            "telegram_user_id": telegram_user_id,
            "is_blocked_candidate": int(is_blocked_candidate),
            "blocked_at": _sqlite_dt(blocked_at),
        },
    )


async def _has_blocked(
    session: SyncExecuteSession,
    *,
    telegram_user_id: int,
    blocked_since: datetime,
) -> bool:
    return await TelegramDeliveryAttemptsRepo.has_blocked_candidate(
        cast(AsyncSession, session),
        telegram_user_id=telegram_user_id,
        blocked_since=blocked_since,
    )


async def test_blocked_candidate_policy_expires_and_clears_after_inbound_activity() -> None:
    base_time = datetime(2026, 7, 10, 12, 0)
    blocked_since = base_time - timedelta(days=30)
    engine, connection = _create_connection()
    session = SyncExecuteSession(connection)
    try:
        _insert_blocked_attempt(
            connection,
            row_id=1,
            telegram_user_id=101,
            blocked_at=base_time - timedelta(days=1),
        )
        assert await _has_blocked(
            session,
            telegram_user_id=101,
            blocked_since=blocked_since,
        )

        _insert_blocked_attempt(
            connection,
            row_id=2,
            telegram_user_id=102,
            blocked_at=base_time - timedelta(days=31),
        )
        assert not await _has_blocked(
            session,
            telegram_user_id=102,
            blocked_since=blocked_since,
        )

        _insert_blocked_attempt(
            connection,
            row_id=3,
            telegram_user_id=103,
            blocked_at=base_time - timedelta(days=1),
        )
        connection.execute(
            text(
                """
                INSERT INTO users (id, telegram_user_id, last_seen_at)
                VALUES (1, 103, :last_seen_at)
                """
            ),
            {"last_seen_at": _sqlite_dt(base_time)},
        )
        assert not await _has_blocked(
            session,
            telegram_user_id=103,
            blocked_since=blocked_since,
        )

        _insert_blocked_attempt(
            connection,
            row_id=4,
            telegram_user_id=104,
            blocked_at=base_time - timedelta(days=1),
            is_blocked_candidate=False,
        )
        assert not await _has_blocked(
            session,
            telegram_user_id=104,
            blocked_since=blocked_since,
        )
    finally:
        connection.close()
        engine.dispose()
