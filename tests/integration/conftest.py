from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.integration_db_safety import assert_safe_integration_db
from app.db.session import engine
from app.game.questions.runtime_bank import clear_question_pool_cache

TRUNCATE_TABLES = (
    "daily_metrics",
    "promo_audit_log",
    "admins",
    "promo_attempts",
    "promo_redemptions",
    "contact_requests",
    "referrals",
    "offers_impressions",
    "quiz_attempts",
    "daily_push_logs",
    "daily_question_sets",
    "daily_runs",
    "quiz_questions",
    "quiz_sessions",
    "friend_challenges",
    "tournament_round_scores",
    "tournament_matches",
    "tournament_participants",
    "tournaments",
    "mode_progress",
    "entitlements",
    "ledger_entries",
    "purchases",
    "processed_updates",
    "outbox_events",
    "telegram_delivery_attempts",
    "analytics_events",
    "analytics_daily",
    "reconciliation_runs",
    "promo_codes",
    "promo_code_batches",
    "streak_state",
    "energy_state",
    "users",
)


@pytest.fixture(scope="session", autouse=True)
def guard_integration_db_target() -> None:
    assert_safe_integration_db(str(engine.url))


async def _existing_truncate_sql() -> str | None:
    quoted_tables = ", ".join(f"'{table_name}'" for table_name in TRUNCATE_TABLES)
    stmt = text(
        "SELECT tablename FROM pg_tables "
        "WHERE schemaname = 'public' AND tablename IN (" + quoted_tables + ")"
    )
    async with engine.connect() as conn:
        result = await conn.execute(stmt)
    existing_table_names = {str(value) for value in result.scalars().all()}
    # Keep a deterministic lock order across cleanup runs to avoid TRUNCATE deadlocks.
    existing_tables = [
        table_name for table_name in TRUNCATE_TABLES if table_name in existing_table_names
    ]
    if not existing_tables:
        return None
    return f"TRUNCATE TABLE {', '.join(existing_tables)} RESTART IDENTITY CASCADE"


async def _truncate_with_retry(truncate_sql: str) -> None:
    for attempt in range(1, 4):
        try:
            async with engine.begin() as conn:
                await conn.execute(text(truncate_sql))
            return
        except DBAPIError as exc:
            if "deadlock detected" not in str(exc).lower() or attempt == 3:
                raise
            await engine.dispose()
            await asyncio.sleep(0.2 * attempt)


@pytest.fixture(autouse=True)
async def cleanup_db() -> AsyncGenerator[None, None]:
    # Dispose pooled connections between tests to avoid cross-event-loop asyncpg reuse.
    await engine.dispose()
    clear_question_pool_cache()

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"Postgres is required for integration tests: {exc}")

    truncate_sql = await _existing_truncate_sql()
    if truncate_sql is not None:
        await _truncate_with_retry(truncate_sql)

    yield

    clear_question_pool_cache()
    await engine.dispose()
