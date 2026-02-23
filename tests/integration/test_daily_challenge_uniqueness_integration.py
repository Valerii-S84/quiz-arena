from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.models.quiz_sessions import QuizSession
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=60_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="DailyChallenge",
            referred_by_user_id=None,
        )
        return user.id


@pytest.mark.asyncio
async def test_daily_challenge_unique_index_blocks_duplicate_per_user_day() -> None:
    user_id = await _create_user("daily-challenge-unique")
    local_date = date(2026, 2, 18)
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)

    async with SessionLocal.begin() as session:
        await session.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_challenge_user_date "
                "ON quiz_sessions (user_id, local_date_berlin) WHERE source = 'DAILY_CHALLENGE'"
            )
        )

        session.add(
            QuizSession(
                id=uuid4(),
                user_id=user_id,
                mode_code="DAILY_CHALLENGE",
                source="DAILY_CHALLENGE",
                status="STARTED",
                energy_cost_total=0,
                question_id="dc_2026-02-18",
                started_at=now_utc,
                local_date_berlin=local_date,
                idempotency_key="daily-unique-1",
            )
        )
        await session.flush()

        session.add(
            QuizSession(
                id=uuid4(),
                user_id=user_id,
                mode_code="DAILY_CHALLENGE",
                source="DAILY_CHALLENGE",
                status="STARTED",
                energy_cost_total=0,
                question_id="dc_2026-02-18",
                started_at=now_utc,
                local_date_berlin=local_date,
                idempotency_key="daily-unique-2",
            )
        )

        with pytest.raises(IntegrityError):
            await session.flush()
