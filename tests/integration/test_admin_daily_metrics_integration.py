from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.db.models.daily_metrics import DailyMetrics
from app.db.models.entitlements import Entitlement
from app.db.models.purchases import Purchase
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.workers.tasks import admin_daily_metrics
from tests.integration.stable_ids import stable_telegram_user_id

UTC = timezone.utc


class _FixedDateTime(datetime):
    fixed_now = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        if tz is None:
            return cls.fixed_now.replace(tzinfo=None)
        return cls.fixed_now.astimezone(tz)


def _freeze_now(monkeypatch: pytest.MonkeyPatch, fixed_now: datetime) -> None:
    _FixedDateTime.fixed_now = fixed_now
    monkeypatch.setattr(admin_daily_metrics, "datetime", _FixedDateTime)


@pytest.fixture(autouse=True)
async def _cleanup_daily_metrics() -> None:
    async with SessionLocal.begin() as session:
        await session.execute(delete(DailyMetrics))
    yield
    async with SessionLocal.begin() as session:
        await session.execute(delete(DailyMetrics))


async def _create_user(
    session,
    *,
    seed: str,
    created_at: datetime,
    last_seen_at: datetime | None,
) -> int:
    user = await UsersRepo.create(
        session,
        telegram_user_id=stable_telegram_user_id(prefix=81_000_000_000, seed=seed),
        referral_code=f"A{uuid4().hex[:10].upper()}",
        username=seed,
        first_name=seed,
        referred_by_user_id=None,
    )
    user.created_at = created_at
    user.last_seen_at = last_seen_at
    return int(user.id)


def _build_purchase(
    *,
    user_id: int,
    stars_amount: int,
    status: str,
    created_at: datetime,
    paid_at: datetime | None,
) -> Purchase:
    return Purchase(
        id=uuid4(),
        user_id=user_id,
        product_code=f"PREMIUM_{uuid4().hex[:8].upper()}",
        product_type="PREMIUM",
        base_stars_amount=stars_amount,
        discount_stars_amount=0,
        stars_amount=stars_amount,
        currency="XTR",
        status=status,
        applied_promo_code_id=None,
        idempotency_key=f"admin-metrics-purchase:{uuid4()}",
        invoice_payload=f"admin-metrics-invoice:{uuid4()}",
        telegram_payment_charge_id=None,
        telegram_pre_checkout_query_id=None,
        raw_successful_payment=None,
        created_at=created_at,
        paid_at=paid_at,
        credited_at=paid_at if status == "CREDITED" else None,
        refunded_at=paid_at if status == "REFUNDED" else None,
    )


def _build_quiz_session(*, user_id: int, started_at: datetime, local_day: date) -> QuizSession:
    return QuizSession(
        id=uuid4(),
        user_id=user_id,
        mode_code="ARTIKEL_SPRINT",
        source="MENU",
        status="COMPLETED",
        energy_cost_total=1,
        question_id="q-admin-metrics",
        friend_challenge_id=None,
        friend_challenge_round=None,
        started_at=started_at,
        completed_at=started_at + timedelta(minutes=2),
        local_date_berlin=local_day,
        idempotency_key=f"admin-metrics-session:{uuid4()}",
    )


def _build_entitlement(
    *,
    user_id: int,
    status: str,
    starts_at: datetime,
    ends_at: datetime | None,
) -> Entitlement:
    now = starts_at
    return Entitlement(
        user_id=user_id,
        entitlement_type="PREMIUM",
        scope=None,
        status=status,
        starts_at=starts_at,
        ends_at=ends_at,
        source_purchase_id=None,
        idempotency_key=f"admin-metrics-entitlement:{uuid4()}",
        metadata_={},
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_admin_daily_metrics_clamps_days_back_to_valid_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_now = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    _freeze_now(monkeypatch, fixed_now)

    zero_result = await admin_daily_metrics.run_admin_daily_metrics_aggregation_async(days_back=0)
    negative_result = await admin_daily_metrics.run_admin_daily_metrics_aggregation_async(
        days_back=-3
    )
    max_result = await admin_daily_metrics.run_admin_daily_metrics_aggregation_async(days_back=99)

    async with SessionLocal.begin() as session:
        rows = list(
            (
                await session.execute(select(DailyMetrics).order_by(DailyMetrics.date.desc()))
            ).scalars()
        )

    assert zero_result["days_processed"] == 1
    assert zero_result["dates"] == ["2026-04-10"]
    assert negative_result["days_processed"] == 1
    assert negative_result["dates"] == ["2026-04-10"]
    assert max_result["days_processed"] == 14
    assert max_result["dates"][0] == "2026-04-10"
    assert max_result["dates"][-1] == "2026-03-28"
    assert len(rows) == 14


@pytest.mark.asyncio
async def test_admin_daily_metrics_respects_berlin_day_boundaries_and_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_now = datetime(2026, 3, 29, 12, 0, tzinfo=UTC)
    local_day = date(2026, 3, 29)
    _freeze_now(monkeypatch, fixed_now)
    day_start, day_end = admin_daily_metrics._day_bounds_utc(local_day)

    async with SessionLocal.begin() as session:
        included_user = await _create_user(
            session,
            seed="admin-metrics-dst-included-1",
            created_at=day_start,
            last_seen_at=day_start,
        )
        included_user_2 = await _create_user(
            session,
            seed="admin-metrics-dst-included-2",
            created_at=day_end - timedelta(minutes=1),
            last_seen_at=day_end - timedelta(seconds=1),
        )
        excluded_old_user = await _create_user(
            session,
            seed="admin-metrics-dst-old",
            created_at=day_start - timedelta(days=40),
            last_seen_at=day_start - timedelta(seconds=1),
        )
        excluded_end_user = await _create_user(
            session,
            seed="admin-metrics-dst-end",
            created_at=day_end,
            last_seen_at=day_end,
        )

        session.add_all(
            [
                _build_purchase(
                    user_id=included_user,
                    stars_amount=50,
                    status="CREDITED",
                    created_at=day_start + timedelta(minutes=5),
                    paid_at=day_start + timedelta(hours=1),
                ),
                _build_purchase(
                    user_id=included_user_2,
                    stars_amount=30,
                    status="PAID_UNCREDITED",
                    created_at=day_end - timedelta(hours=1),
                    paid_at=day_end - timedelta(minutes=1),
                ),
                _build_purchase(
                    user_id=included_user,
                    stars_amount=99,
                    status="FAILED",
                    created_at=day_start + timedelta(hours=2),
                    paid_at=day_start + timedelta(hours=2),
                ),
                _build_purchase(
                    user_id=included_user,
                    stars_amount=77,
                    status="REFUNDED",
                    created_at=day_start + timedelta(hours=3),
                    paid_at=day_start + timedelta(hours=3),
                ),
                _build_purchase(
                    user_id=excluded_old_user,
                    stars_amount=88,
                    status="CREDITED",
                    created_at=day_start - timedelta(minutes=10),
                    paid_at=day_start - timedelta(seconds=1),
                ),
            ]
        )
        session.add_all(
            [
                _build_quiz_session(
                    user_id=included_user,
                    started_at=day_start + timedelta(minutes=30),
                    local_day=local_day,
                ),
                _build_quiz_session(
                    user_id=excluded_end_user,
                    started_at=day_end,
                    local_day=local_day,
                ),
            ]
        )
        session.add_all(
            [
                _build_entitlement(
                    user_id=included_user,
                    status="ACTIVE",
                    starts_at=day_start - timedelta(days=1),
                    ends_at=day_end + timedelta(days=5),
                ),
                _build_entitlement(
                    user_id=included_user_2,
                    status="EXPIRED",
                    starts_at=day_start - timedelta(days=2),
                    ends_at=day_end + timedelta(days=1),
                ),
                _build_entitlement(
                    user_id=excluded_old_user,
                    status="ACTIVE",
                    starts_at=day_end + timedelta(seconds=1),
                    ends_at=day_end + timedelta(days=3),
                ),
                _build_entitlement(
                    user_id=excluded_end_user,
                    status="ACTIVE",
                    starts_at=day_start - timedelta(days=3),
                    ends_at=day_end - timedelta(seconds=1),
                ),
            ]
        )

    result = await admin_daily_metrics.run_admin_daily_metrics_aggregation_async(days_back=1)

    async with SessionLocal.begin() as session:
        row = await session.get(DailyMetrics, local_day)

    assert result["days_processed"] == 1
    assert row is not None
    assert row.date == local_day
    assert row.dau == 2
    assert row.wau == 3
    assert row.mau == 3
    assert row.new_users == 2
    assert row.revenue_stars == 80
    assert row.revenue_eur == Decimal("1.60")
    assert row.quizzes_played == 1
    assert row.purchases_count == 2
    assert row.active_subscriptions == 1


@pytest.mark.asyncio
async def test_admin_daily_metrics_upserts_existing_rows_and_writes_multiple_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_now = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    today = date(2026, 4, 10)
    yesterday = date(2026, 4, 9)
    _freeze_now(monkeypatch, fixed_now)
    today_start, _today_end = admin_daily_metrics._day_bounds_utc(today)
    yesterday_start, yesterday_end = admin_daily_metrics._day_bounds_utc(yesterday)

    async with SessionLocal.begin() as session:
        today_user = await _create_user(
            session,
            seed="admin-metrics-today",
            created_at=today_start + timedelta(minutes=5),
            last_seen_at=today_start + timedelta(hours=1),
        )
        yesterday_user = await _create_user(
            session,
            seed="admin-metrics-yesterday",
            created_at=yesterday_start + timedelta(minutes=5),
            last_seen_at=yesterday_start + timedelta(hours=1),
        )
        session.add_all(
            [
                _build_purchase(
                    user_id=today_user,
                    stars_amount=40,
                    status="CREDITED",
                    created_at=today_start + timedelta(minutes=10),
                    paid_at=today_start + timedelta(minutes=11),
                ),
                _build_purchase(
                    user_id=yesterday_user,
                    stars_amount=25,
                    status="PAID_UNCREDITED",
                    created_at=yesterday_start + timedelta(minutes=10),
                    paid_at=yesterday_start + timedelta(minutes=11),
                ),
            ]
        )
        session.add(
            _build_quiz_session(
                user_id=yesterday_user,
                started_at=yesterday_end - timedelta(minutes=30),
                local_day=yesterday,
            )
        )

    first_result = await admin_daily_metrics.run_admin_daily_metrics_aggregation_async(days_back=2)

    async with SessionLocal.begin() as session:
        initial_rows = list(
            (
                await session.execute(select(DailyMetrics).order_by(DailyMetrics.date.asc()))
            ).scalars()
        )

    assert first_result["days_processed"] == 2
    assert [row.date for row in initial_rows] == [yesterday, today]
    assert initial_rows[0].revenue_stars == 25
    assert initial_rows[0].purchases_count == 1
    assert initial_rows[0].quizzes_played == 1
    assert initial_rows[1].revenue_stars == 40
    assert initial_rows[1].purchases_count == 1

    async with SessionLocal.begin() as session:
        today_user = int(
            (
                await session.execute(
                    select(func.min(Purchase.user_id)).where(
                        Purchase.paid_at >= today_start,
                        Purchase.paid_at < today_start + timedelta(days=1),
                    )
                )
            ).scalar_one()
        )
        session.add(
            _build_purchase(
                user_id=today_user,
                stars_amount=10,
                status="CREDITED",
                created_at=today_start + timedelta(hours=2),
                paid_at=today_start + timedelta(hours=2, minutes=1),
            )
        )

    second_result = await admin_daily_metrics.run_admin_daily_metrics_aggregation_async(days_back=2)

    async with SessionLocal.begin() as session:
        updated_rows = list(
            (
                await session.execute(select(DailyMetrics).order_by(DailyMetrics.date.asc()))
            ).scalars()
        )

    assert second_result["days_processed"] == 2
    assert len(updated_rows) == 2
    assert updated_rows[0].date == yesterday
    assert updated_rows[0].revenue_stars == 25
    assert updated_rows[0].purchases_count == 1
    assert updated_rows[1].date == today
    assert updated_rows[1].revenue_stars == 50
    assert updated_rows[1].purchases_count == 2
