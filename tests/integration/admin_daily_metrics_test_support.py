from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entitlements import Entitlement
from app.db.models.purchases import Purchase
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.users_repo import UsersRepo
from app.workers.tasks import admin_daily_metrics
from tests.integration.stable_ids import stable_telegram_user_id

UTC = timezone.utc


class FixedDateTime(datetime):
    fixed_now = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        if tz is None:
            return cls.fixed_now.replace(tzinfo=None)
        return cls.fixed_now.astimezone(tz)


def freeze_now(monkeypatch: pytest.MonkeyPatch, fixed_now: datetime) -> None:
    FixedDateTime.fixed_now = fixed_now
    monkeypatch.setattr(admin_daily_metrics, "datetime", FixedDateTime)


async def create_user(
    session: AsyncSession,
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


def build_purchase(
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


def build_quiz_session(*, user_id: int, started_at: datetime, local_day: date) -> QuizSession:
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


def build_entitlement(
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
