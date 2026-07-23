from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entitlements import Entitlement
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from tests.integration.stable_ids import stable_telegram_user_id

NOW_UTC = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)


async def _add_entitlement(
    session: AsyncSession,
    *,
    seed: str,
    entitlement_type: str = "PREMIUM",
    status: str = "ACTIVE",
    ends_at: datetime | None = None,
) -> int:
    user = await UsersRepo.create(
        session,
        telegram_user_id=stable_telegram_user_id(prefix=60_000_000_000, seed=seed),
        referral_code=f"R{uuid4().hex[:10]}",
        username=None,
        first_name="Premium expiry",
        referred_by_user_id=None,
    )
    entitlement = Entitlement(
        user_id=user.id,
        entitlement_type=entitlement_type,
        scope="PREMIUM_MONTH" if entitlement_type == "PREMIUM" else "ARENA_DUELS",
        status=status,
        starts_at=NOW_UTC - timedelta(days=30),
        ends_at=ends_at,
        source_purchase_id=None,
        idempotency_key=f"premium-expiry:{seed}",
        metadata_={},
        created_at=NOW_UTC - timedelta(days=30),
        updated_at=NOW_UTC - timedelta(days=1),
    )
    session.add(entitlement)
    await session.flush()
    return entitlement.id


async def _statuses(entitlement_ids: list[int]) -> dict[int, str]:
    async with SessionLocal.begin() as session:
        rows = await session.execute(
            select(Entitlement.id, Entitlement.status).where(Entitlement.id.in_(entitlement_ids))
        )
        return {int(row_id): str(status) for row_id, status in rows.all()}


@pytest.mark.asyncio
async def test_expiry_transitions_only_due_active_premium_entitlements() -> None:
    async with SessionLocal.begin() as session:
        entitlement_ids = {
            "due": await _add_entitlement(
                session,
                seed="due-active-premium",
                ends_at=NOW_UTC - timedelta(seconds=1),
            ),
            "future": await _add_entitlement(
                session,
                seed="future-active-premium",
                ends_at=NOW_UTC + timedelta(seconds=1),
            ),
            "perpetual": await _add_entitlement(
                session,
                seed="perpetual-active-premium",
                ends_at=None,
            ),
            "scheduled": await _add_entitlement(
                session,
                seed="scheduled-due-premium",
                status="SCHEDULED",
                ends_at=NOW_UTC - timedelta(days=1),
            ),
            "expired": await _add_entitlement(
                session,
                seed="already-expired-premium",
                status="EXPIRED",
                ends_at=NOW_UTC - timedelta(days=1),
            ),
            "other_type": await _add_entitlement(
                session,
                seed="due-mode-access",
                entitlement_type="MODE_ACCESS",
                ends_at=NOW_UTC - timedelta(days=1),
            ),
        }

    async with SessionLocal.begin() as session:
        before_count = await EntitlementsRepo.count_expired_active_premium(
            session,
            now_utc=NOW_UTC,
        )
        expired_total = await EntitlementsRepo.expire_active_premium_before(
            session,
            now_utc=NOW_UTC,
            limit=100,
        )

    statuses = await _statuses(list(entitlement_ids.values()))
    assert before_count == 1
    assert expired_total == 1
    assert statuses[entitlement_ids["due"]] == "EXPIRED"
    assert statuses[entitlement_ids["future"]] == "ACTIVE"
    assert statuses[entitlement_ids["perpetual"]] == "ACTIVE"
    assert statuses[entitlement_ids["scheduled"]] == "SCHEDULED"
    assert statuses[entitlement_ids["expired"]] == "EXPIRED"
    assert statuses[entitlement_ids["other_type"]] == "ACTIVE"


@pytest.mark.asyncio
async def test_expiry_drains_repeated_bounded_batches() -> None:
    async with SessionLocal.begin() as session:
        entitlement_ids = [
            await _add_entitlement(
                session,
                seed=f"bounded-{index}",
                ends_at=NOW_UTC - timedelta(minutes=5 - index),
            )
            for index in range(5)
        ]

    batch_results: list[int] = []
    for _ in range(4):
        async with SessionLocal.begin() as session:
            batch_results.append(
                await EntitlementsRepo.expire_active_premium_before(
                    session,
                    now_utc=NOW_UTC,
                    limit=2,
                )
            )

    assert batch_results == [2, 2, 1, 0]
    assert set((await _statuses(entitlement_ids)).values()) == {"EXPIRED"}


@pytest.mark.asyncio
async def test_expiry_skips_rows_locked_by_concurrent_worker() -> None:
    async with SessionLocal.begin() as session:
        entitlement_ids = [
            await _add_entitlement(
                session,
                seed=f"locked-{index}",
                ends_at=NOW_UTC - timedelta(minutes=2 - index),
            )
            for index in range(2)
        ]

    async with SessionLocal.begin() as lock_session:
        locked_id = await lock_session.scalar(
            select(Entitlement.id)
            .where(Entitlement.id.in_(entitlement_ids))
            .order_by(Entitlement.ends_at.asc(), Entitlement.id.asc())
            .limit(1)
            .with_for_update()
        )
        assert locked_id is not None

        async with SessionLocal.begin() as worker_session:
            processed_while_locked = await EntitlementsRepo.expire_active_premium_before(
                worker_session,
                now_utc=NOW_UTC,
                limit=2,
            )

        statuses_while_locked = await _statuses(entitlement_ids)
        assert processed_while_locked == 1
        assert statuses_while_locked[int(locked_id)] == "ACTIVE"

    async with SessionLocal.begin() as session:
        processed_after_unlock = await EntitlementsRepo.expire_active_premium_before(
            session,
            now_utc=NOW_UTC,
            limit=2,
        )

    assert processed_after_unlock == 1
    assert set((await _statuses(entitlement_ids)).values()) == {"EXPIRED"}
