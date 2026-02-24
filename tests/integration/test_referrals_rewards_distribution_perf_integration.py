from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import Connection

from app.db.models.referrals import Referral
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal, engine
from app.economy.referrals.service import ReferralService

UTC = timezone.utc


def _utc_now(
    *,
    year: int,
    month: int,
    day: int,
    hour: int = 12,
    minute: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


async def _create_user(session, *, seed: int) -> tuple[int, str]:
    user = await UsersRepo.create(
        session,
        telegram_user_id=80_000_000_000 + seed,
        referral_code=f"R{uuid4().hex[:10].upper()}",
        username=None,
        first_name="ReferralPerf",
        referred_by_user_id=None,
    )
    return int(user.id), str(user.referral_code)


async def _create_referrals(
    session,
    *,
    referrer_user_id: int,
    referral_code: str,
    statuses: list[str],
    qualified_at: datetime,
    rewarded_at: datetime | None = None,
    seed_start: int,
) -> None:
    for offset, status in enumerate(statuses):
        referred_user_id, _ = await _create_user(session, seed=seed_start + offset)
        session.add(
            Referral(
                referrer_user_id=referrer_user_id,
                referred_user_id=referred_user_id,
                referral_code=referral_code,
                status=status,
                qualified_at=qualified_at,
                rewarded_at=rewarded_at if status == "REWARDED" else None,
                fraud_score=0,
                created_at=qualified_at - timedelta(days=2),
            )
        )
    await session.flush()


async def _count_status(session, *, referrer_user_id: int, status: str) -> int:
    stmt = select(func.count(Referral.id)).where(
        Referral.referrer_user_id == referrer_user_id,
        Referral.status == status,
    )
    return int(await session.scalar(stmt) or 0)


@pytest.mark.asyncio
async def test_reward_distribution_preserves_invariants_for_cap_status_and_sum() -> None:
    now_utc = _utc_now(year=2026, month=2, day=20)
    qualified_old = now_utc - timedelta(hours=72)
    qualified_recent = now_utc - timedelta(hours=47)

    async with SessionLocal.begin() as session:
        referrer_open, ref_code_open = await _create_user(session, seed=1)
        await _create_referrals(
            session,
            referrer_user_id=referrer_open,
            referral_code=ref_code_open,
            statuses=["QUALIFIED", "QUALIFIED", "QUALIFIED"],
            qualified_at=qualified_old,
            seed_start=10_000,
        )

        referrer_resume, ref_code_resume = await _create_user(session, seed=2)
        await _create_referrals(
            session,
            referrer_user_id=referrer_resume,
            referral_code=ref_code_resume,
            statuses=["QUALIFIED", "QUALIFIED", "DEFERRED_LIMIT"],
            qualified_at=qualified_old,
            seed_start=20_000,
        )

        referrer_capped, ref_code_capped = await _create_user(session, seed=3)
        await _create_referrals(
            session,
            referrer_user_id=referrer_capped,
            referral_code=ref_code_capped,
            statuses=["REWARDED"] * 6,
            qualified_at=qualified_old,
            rewarded_at=now_utc - timedelta(days=1),
            seed_start=30_000,
        )
        await _create_referrals(
            session,
            referrer_user_id=referrer_capped,
            referral_code=ref_code_capped,
            statuses=["QUALIFIED", "QUALIFIED", "QUALIFIED"],
            qualified_at=qualified_old,
            seed_start=40_000,
        )

        referrer_not_ready, ref_code_not_ready = await _create_user(session, seed=4)
        await _create_referrals(
            session,
            referrer_user_id=referrer_not_ready,
            referral_code=ref_code_not_ready,
            statuses=["QUALIFIED", "QUALIFIED", "QUALIFIED"],
            qualified_at=qualified_recent,
            seed_start=50_000,
        )

    async with SessionLocal.begin() as session:
        result = await ReferralService.run_reward_distribution(
            session,
            now_utc=now_utc,
            reward_code=None,
        )

    assert result["referrers_examined"] == 3
    assert result["rewards_granted"] == 0
    assert result["awaiting_choice"] == 2
    assert result["deferred_limit"] == 1

    async with SessionLocal.begin() as session:
        assert (
            await _count_status(
                session,
                referrer_user_id=referrer_resume,
                status="DEFERRED_LIMIT",
            )
            == 0
        )
        assert (
            await _count_status(
                session,
                referrer_user_id=referrer_resume,
                status="QUALIFIED",
            )
            == 3
        )

        assert (
            await _count_status(
                session,
                referrer_user_id=referrer_capped,
                status="REWARDED",
            )
            == 6
        )
        assert (
            await _count_status(
                session,
                referrer_user_id=referrer_capped,
                status="DEFERRED_LIMIT",
            )
            == 1
        )

        assert (
            await _count_status(
                session,
                referrer_user_id=referrer_open,
                status="DEFERRED_LIMIT",
            )
            == 0
        )
        assert (
            await _count_status(
                session,
                referrer_user_id=referrer_not_ready,
                status="QUALIFIED",
            )
            == 3
        )


@pytest.mark.asyncio
async def test_reward_distribution_query_count_is_bounded() -> None:
    now_utc = _utc_now(year=2026, month=2, day=21)
    qualified_old = now_utc - timedelta(hours=72)

    async with SessionLocal.begin() as session:
        for referrer_seed in range(100, 160):
            referrer_user_id, referral_code = await _create_user(session, seed=referrer_seed)
            await _create_referrals(
                session,
                referrer_user_id=referrer_user_id,
                referral_code=referral_code,
                statuses=["QUALIFIED", "QUALIFIED", "QUALIFIED"],
                qualified_at=qualified_old,
                seed_start=referrer_seed * 1_000,
            )

    query_count = 0

    def _before_cursor_execute(
        conn: Connection,
        cursor,
        statement: str,
        parameters,
        context,
        executemany: bool,
    ) -> None:
        nonlocal query_count
        del conn, cursor, statement, parameters, context, executemany
        query_count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        async with SessionLocal.begin() as session:
            result = await ReferralService.run_reward_distribution(
                session,
                now_utc=now_utc,
                reward_code=None,
            )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)

    assert result["referrers_examined"] == 60
    assert result["awaiting_choice"] == 60
    assert query_count <= 10
