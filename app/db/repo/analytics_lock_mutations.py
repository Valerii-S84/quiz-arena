from __future__ import annotations

from hashlib import sha256

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


async def lock_arena_beaten_notification_event_key(
    session: AsyncSession,
    *,
    event_type: str,
    user_id: int,
    payload: dict[str, object],
) -> None:
    await _lock_analytics_key(
        session,
        (
            event_type,
            str(user_id),
            str(payload["arena_duel_id"]),
            str(payload["previous_best_attempt_id"]),
            str(payload["new_best_attempt_id"]),
            str(payload["notification_type"]),
        ),
    )


async def lock_arena_revanche_event_key(
    session: AsyncSession,
    *,
    event_type: str,
    user_id: int,
    payload: dict[str, object],
) -> None:
    await _lock_analytics_key(
        session,
        (
            event_type,
            str(user_id),
            str(payload["revanche_receiver_id"]),
            str(payload["source_attempt_id"]),
            str(payload["notification_type"]),
        ),
    )


async def lock_arena_revanche_sender_quota(
    session: AsyncSession,
    *,
    user_id: int,
) -> None:
    await _lock_analytics_key(session, ("arena_revanche_sender_quota", str(user_id)))


async def _lock_analytics_key(session: AsyncSession, parts: tuple[str, ...]) -> None:
    digest = sha256("|".join(parts).encode("utf-8")).digest()
    lock_key_1 = int.from_bytes(digest[:4], byteorder="big", signed=True)
    lock_key_2 = int.from_bytes(digest[4:8], byteorder="big", signed=True)
    await session.execute(
        sa.text("SELECT pg_advisory_xact_lock(:lock_key_1, :lock_key_2)"),
        {"lock_key_1": lock_key_1, "lock_key_2": lock_key_2},
    )
