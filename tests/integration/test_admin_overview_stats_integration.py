from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.api.routes.admin.overview_queries import build_overview_payload
from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.purchases import Purchase
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from tests.integration.stable_ids import stable_telegram_user_id

UTC = timezone.utc


async def _create_user(
    *,
    seed: str,
    created_at: datetime,
    last_seen_at: datetime | None,
) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=stable_telegram_user_id(prefix=81_000_000_000, seed=seed),
            referral_code=f"O{uuid4().hex[:10].upper()}",
            username=seed,
            first_name=seed,
            referred_by_user_id=None,
        )
        user.created_at = created_at
        user.last_seen_at = last_seen_at
        return int(user.id)


def _quiz_session(
    *,
    user_id: int,
    started_at: datetime,
    completed_at: datetime | None,
    local_day: date,
    status: str,
    suffix: str,
) -> QuizSession:
    return QuizSession(
        id=uuid4(),
        user_id=user_id,
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        status=status,
        energy_cost_total=1,
        question_id=f"q-overview-{suffix}",
        friend_challenge_id=None,
        friend_challenge_round=None,
        started_at=started_at,
        completed_at=completed_at,
        local_date_berlin=local_day,
        idempotency_key=f"overview-stats-session:{suffix}:{uuid4()}",
    )


def _purchase(*, user_id: int, paid_at: datetime, suffix: str) -> Purchase:
    return Purchase(
        id=uuid4(),
        user_id=user_id,
        product_code="PREMIUM_MONTH",
        product_type="PREMIUM",
        base_stars_amount=100,
        discount_stars_amount=0,
        stars_amount=100,
        currency="XTR",
        status="CREDITED",
        applied_promo_code_id=None,
        idempotency_key=f"overview-stats-purchase:{suffix}:{uuid4()}",
        invoice_payload=f"overview-stats-invoice:{suffix}:{uuid4()}",
        telegram_payment_charge_id=None,
        telegram_pre_checkout_query_id=None,
        raw_successful_payment=None,
        created_at=paid_at - timedelta(minutes=5),
        paid_at=paid_at,
        credited_at=paid_at,
        refunded_at=None,
    )


@pytest.mark.asyncio
async def test_overview_payload_uses_first_milestones_and_consistent_activity_model() -> None:
    now_utc = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    user_a = await _create_user(
        seed="overview-a",
        created_at=datetime(2026, 4, 5, 9, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 4, 5, 9, 0, tzinfo=UTC),
    )
    user_b = await _create_user(
        seed="overview-b",
        created_at=datetime(2026, 4, 5, 10, 0, tzinfo=UTC),
        last_seen_at=None,
    )
    user_c = await _create_user(
        seed="overview-c",
        created_at=datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
    )

    async with SessionLocal.begin() as session:
        session.add_all(
            [
                _quiz_session(
                    user_id=user_a,
                    started_at=datetime(2026, 4, 6, 8, 0, tzinfo=UTC),
                    completed_at=datetime(2026, 4, 6, 8, 2, tzinfo=UTC),
                    local_day=date(2026, 4, 6),
                    status="COMPLETED",
                    suffix="a1",
                ),
                _quiz_session(
                    user_id=user_a,
                    started_at=datetime(2026, 4, 7, 8, 0, tzinfo=UTC),
                    completed_at=datetime(2026, 4, 7, 8, 2, tzinfo=UTC),
                    local_day=date(2026, 4, 7),
                    status="COMPLETED",
                    suffix="a2",
                ),
                _quiz_session(
                    user_id=user_a,
                    started_at=datetime(2026, 4, 8, 8, 0, tzinfo=UTC),
                    completed_at=datetime(2026, 4, 8, 8, 2, tzinfo=UTC),
                    local_day=date(2026, 4, 8),
                    status="COMPLETED",
                    suffix="a3",
                ),
                _quiz_session(
                    user_id=user_c,
                    started_at=datetime(2026, 3, 25, 8, 0, tzinfo=UTC),
                    completed_at=datetime(2026, 3, 25, 8, 2, tzinfo=UTC),
                    local_day=date(2026, 3, 25),
                    status="COMPLETED",
                    suffix="c1",
                ),
                _quiz_session(
                    user_id=user_c,
                    started_at=datetime(2026, 4, 10, 8, 0, tzinfo=UTC),
                    completed_at=datetime(2026, 4, 10, 8, 2, tzinfo=UTC),
                    local_day=date(2026, 4, 10),
                    status="COMPLETED",
                    suffix="c2",
                ),
            ]
        )
        session.add(
            _purchase(user_id=user_a, paid_at=datetime(2026, 4, 9, 10, 0, tzinfo=UTC), suffix="a1")
        )
        await emit_analytics_event(
            session,
            event_type="bot_started",
            source=EVENT_SOURCE_BOT,
            happened_at=datetime(2026, 4, 6, 9, 0, tzinfo=UTC),
            user_id=user_b,
            payload={"start_source": "direct"},
        )
        await emit_analytics_event(
            session,
            event_type="bot_started",
            source=EVENT_SOURCE_BOT,
            happened_at=datetime(2026, 4, 10, 9, 0, tzinfo=UTC),
            user_id=user_b,
            payload={"start_source": "direct"},
        )

    async with SessionLocal.begin() as session:
        payload = await build_overview_payload(session, now_utc=now_utc, days=7)

    assert payload["kpis"]["start_users"]["current"] == 2.0
    assert payload["kpis"]["conversion_start_to_quiz"]["current"] == 50.0
    assert payload["kpis"]["retention_d1"]["current"] == 100.0
    assert payload["kpis"]["dau"]["current"] == 2.0
    assert payload["funnel"] == [
        {"step": "Start", "value": 2},
        {"step": "First Quiz", "value": 1},
        {"step": "Streak 3+", "value": 1},
        {"step": "Purchase", "value": 1},
    ]
