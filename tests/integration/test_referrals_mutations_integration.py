from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.models.referrals import Referral
from app.db.repo.referrals_mutations import create, mark_started_as_rejected_fraud
from app.db.session import SessionLocal
from tests.integration.referrals_fixtures import UTC, _create_user


@pytest.mark.asyncio
async def test_referrals_mutations_create_persists_referral() -> None:
    now_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrals-mutations-create-referrer")
    referred = await _create_user("referrals-mutations-create-referred")

    referral = Referral(
        referrer_user_id=referrer.id,
        referred_user_id=referred.id,
        referral_code=referrer.referral_code,
        status="STARTED",
        qualified_at=None,
        rewarded_at=None,
        notified_at=None,
        fraud_score=Decimal("0"),
        created_at=now_utc,
    )

    async with SessionLocal.begin() as session:
        created = await create(session, referral=referral)

    assert created.id is not None

    async with SessionLocal.begin() as session:
        persisted = await session.scalar(select(Referral).where(Referral.id == created.id))

    assert persisted is not None
    assert persisted.referrer_user_id == referrer.id
    assert persisted.referred_user_id == referred.id
    assert persisted.status == "STARTED"


@pytest.mark.asyncio
async def test_mark_started_as_rejected_fraud_updates_only_recent_started_rows() -> None:
    now_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrals-mutations-fraud-referrer")
    recent_started = await _create_user("referrals-mutations-recent-started")
    boundary_started = await _create_user("referrals-mutations-boundary-started")
    old_started = await _create_user("referrals-mutations-old-started")
    qualified = await _create_user("referrals-mutations-qualified")

    min_created_at_utc = now_utc - timedelta(hours=2)

    async with SessionLocal.begin() as session:
        session.add_all(
            [
                Referral(
                    referrer_user_id=referrer.id,
                    referred_user_id=recent_started.id,
                    referral_code=referrer.referral_code,
                    status="STARTED",
                    qualified_at=None,
                    rewarded_at=None,
                    notified_at=None,
                    fraud_score=Decimal("0"),
                    created_at=now_utc - timedelta(hours=1),
                ),
                Referral(
                    referrer_user_id=referrer.id,
                    referred_user_id=boundary_started.id,
                    referral_code=referrer.referral_code,
                    status="STARTED",
                    qualified_at=None,
                    rewarded_at=None,
                    notified_at=None,
                    fraud_score=Decimal("0"),
                    created_at=min_created_at_utc,
                ),
                Referral(
                    referrer_user_id=referrer.id,
                    referred_user_id=old_started.id,
                    referral_code=referrer.referral_code,
                    status="STARTED",
                    qualified_at=None,
                    rewarded_at=None,
                    notified_at=None,
                    fraud_score=Decimal("0"),
                    created_at=now_utc - timedelta(days=1),
                ),
                Referral(
                    referrer_user_id=referrer.id,
                    referred_user_id=qualified.id,
                    referral_code=referrer.referral_code,
                    status="QUALIFIED",
                    qualified_at=now_utc - timedelta(hours=3),
                    rewarded_at=None,
                    notified_at=None,
                    fraud_score=Decimal("0"),
                    created_at=now_utc - timedelta(hours=3),
                ),
            ]
        )

    async with SessionLocal.begin() as session:
        updated_count = await mark_started_as_rejected_fraud(
            session,
            referrer_user_id=referrer.id,
            min_created_at_utc=min_created_at_utc,
            score=Decimal("87.50"),
        )

    assert updated_count == 2

    async with SessionLocal.begin() as session:
        rows = list(
            (
                await session.execute(
                    select(Referral)
                    .where(Referral.referrer_user_id == referrer.id)
                    .order_by(Referral.created_at.asc())
                )
            )
            .scalars()
            .all()
        )

    rows_by_referred = {int(row.referred_user_id): row for row in rows}
    assert rows_by_referred[recent_started.id].status == "REJECTED_FRAUD"
    assert rows_by_referred[recent_started.id].fraud_score == Decimal("87.50")
    assert rows_by_referred[boundary_started.id].status == "REJECTED_FRAUD"
    assert rows_by_referred[boundary_started.id].fraud_score == Decimal("87.50")
    assert rows_by_referred[old_started.id].status == "STARTED"
    assert rows_by_referred[qualified.id].status == "QUALIFIED"
