from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.integration_db_safety import assert_safe_integration_db
from app.db.session import engine

TRUNCATE_TABLES = (
    "promo_attempts",
    "promo_redemptions",
    "referrals",
    "offers_impressions",
    "quiz_attempts",
    "daily_push_logs",
    "daily_question_sets",
    "daily_runs",
    "quiz_questions",
    "quiz_sessions",
    "friend_challenges",
    "mode_access",
    "mode_progress",
    "entitlements",
    "ledger_entries",
    "purchases",
    "processed_updates",
    "outbox_events",
    "analytics_events",
    "analytics_daily",
    "reconciliation_runs",
    "promo_codes",
    "promo_code_batches",
    "streak_state",
    "energy_state",
    "users",
)

TRUNCATE_SQL = f"TRUNCATE TABLE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"


@pytest.fixture(scope="session", autouse=True)
def guard_integration_db_target() -> None:
    assert_safe_integration_db(str(engine.url))


@pytest.fixture(autouse=True)
async def cleanup_db() -> None:
    # Dispose pooled connections between tests to avoid cross-event-loop asyncpg reuse.
    await engine.dispose()

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"Postgres is required for integration tests: {exc}")

    async with engine.begin() as conn:
        await conn.execute(text(TRUNCATE_SQL))

    yield

    await engine.dispose()
