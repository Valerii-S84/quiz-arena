from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.db.models.analytics_daily import AnalyticsDaily
from app.db.models.analytics_events import AnalyticsEvent
from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.models.purchases import Purchase
from app.db.models.quiz_sessions import QuizSession
from app.db.session import SessionLocal
from app.workers.tasks.analytics_daily import run_analytics_daily_aggregation_async
from tests.integration.analytics_daily_fixtures import (
    UTC,
    _berlin_date,
    _create_user,
    _day_bounds_utc,
)

DUEL_FUNNEL_EVENTS = (
    ("duel_menu_opened", "duel_menu_opened_events_total"),
    ("duel_mode_selected", "duel_mode_selected_events_total"),
    ("arena_opened", "arena_opened_events_total"),
    ("arena_duel_created", "arena_duel_created_events_total"),
    ("arena_duel_started", "arena_duel_started_events_total"),
    ("arena_duel_completed", "arena_duel_completed_events_total"),
    ("arena_duel_published", "arena_duel_published_events_total"),
    ("arena_duel_accepted", "arena_duel_accepted_events_total"),
    ("arena_result_shown", "arena_result_shown_events_total"),
    (
        "arena_result_beaten_notification_sent",
        "arena_result_beaten_notification_sent_events_total",
    ),
    ("arena_revanche_clicked", "arena_revanche_clicked_events_total"),
    ("friend_duel_opened", "friend_duel_opened_events_total"),
    ("friend_duel_created", "friend_duel_created_events_total"),
    ("friend_duel_share_clicked", "friend_duel_share_clicked_events_total"),
    ("friend_duel_joined", "friend_duel_joined_events_total"),
    ("friend_duel_started", "friend_duel_started_events_total"),
    ("friend_duel_completed", "friend_duel_completed_events_total"),
    ("friend_duel_published_to_arena", "friend_duel_published_to_arena_events_total"),
    ("friend_duel_revanche_clicked", "friend_duel_revanche_clicked_events_total"),
    ("duel_limit_hit", "duel_limit_hit_events_total"),
    ("duel_paywall_shown", "duel_paywall_shown_events_total"),
    ("duel_ticket_clicked", "duel_ticket_clicked_events_total"),
    ("premium_week_clicked", "premium_week_clicked_events_total"),
)


@pytest.mark.asyncio
async def test_analytics_daily_aggregation_builds_expected_daily_kpis() -> None:
    now_utc = datetime.now(UTC)
    local_day = _berlin_date(now_utc)
    day_start_utc, day_end_utc = _day_bounds_utc(local_day)

    user_1 = await _create_user("analytics-u1", day_start_utc + timedelta(hours=1))
    user_2 = await _create_user("analytics-u2", day_start_utc + timedelta(hours=2))
    user_3 = await _create_user("analytics-u3", day_start_utc + timedelta(hours=3))
    await _create_user("analytics-u4", day_start_utc - timedelta(days=8))

    promo_code_id = 71001
    async with SessionLocal.begin() as session:
        session.add(
            PromoCode(
                id=promo_code_id,
                code_hash="A" * 64,
                code_prefix="AN",
                campaign_name="analytics_campaign",
                promo_type="PERCENT_DISCOUNT",
                grant_premium_days=None,
                discount_percent=25,
                target_scope="PREMIUM_MONTH",
                status="ACTIVE",
                valid_from=day_start_utc - timedelta(days=1),
                valid_until=day_end_utc + timedelta(days=5),
                max_total_uses=None,
                used_total=0,
                max_uses_per_user=1,
                new_users_only=False,
                first_purchase_only=False,
                created_by="tests",
                created_at=now_utc,
                updated_at=now_utc,
            )
        )

        session.add_all(
            [
                Purchase(
                    id=uuid4(),
                    user_id=user_1,
                    product_code="ENERGY_10",
                    product_type="MICRO",
                    base_stars_amount=10,
                    discount_stars_amount=0,
                    stars_amount=10,
                    currency="XTR",
                    status="CREDITED",
                    applied_promo_code_id=None,
                    idempotency_key="analytics-purchase-1",
                    invoice_payload="analytics-invoice-1",
                    telegram_payment_charge_id=None,
                    telegram_pre_checkout_query_id=None,
                    raw_successful_payment=None,
                    created_at=day_start_utc + timedelta(minutes=10),
                    paid_at=day_start_utc + timedelta(minutes=11),
                    credited_at=day_start_utc + timedelta(minutes=12),
                    refunded_at=None,
                ),
                Purchase(
                    id=uuid4(),
                    user_id=user_2,
                    product_code="PREMIUM_MONTH",
                    product_type="PREMIUM",
                    base_stars_amount=99,
                    discount_stars_amount=0,
                    stars_amount=99,
                    currency="XTR",
                    status="CREDITED",
                    applied_promo_code_id=None,
                    idempotency_key="analytics-purchase-2",
                    invoice_payload="analytics-invoice-2",
                    telegram_payment_charge_id=None,
                    telegram_pre_checkout_query_id=None,
                    raw_successful_payment=None,
                    created_at=day_start_utc + timedelta(minutes=20),
                    paid_at=day_start_utc + timedelta(minutes=21),
                    credited_at=day_start_utc + timedelta(minutes=22),
                    refunded_at=None,
                ),
                Purchase(
                    id=uuid4(),
                    user_id=user_3,
                    product_code="PREMIUM_MONTH",
                    product_type="PREMIUM",
                    base_stars_amount=99,
                    discount_stars_amount=25,
                    stars_amount=74,
                    currency="XTR",
                    status="CREDITED",
                    applied_promo_code_id=promo_code_id,
                    idempotency_key="analytics-purchase-3",
                    invoice_payload="analytics-invoice-3",
                    telegram_payment_charge_id=None,
                    telegram_pre_checkout_query_id=None,
                    raw_successful_payment=None,
                    created_at=day_start_utc + timedelta(minutes=30),
                    paid_at=day_start_utc + timedelta(minutes=31),
                    credited_at=day_start_utc + timedelta(minutes=32),
                    refunded_at=None,
                ),
            ]
        )

        session.add_all(
            [
                PromoRedemption(
                    id=uuid4(),
                    promo_code_id=promo_code_id,
                    user_id=user_3,
                    status="APPLIED",
                    reject_reason=None,
                    reserved_until=None,
                    applied_purchase_id=None,
                    grant_entitlement_id=None,
                    idempotency_key="analytics-redemption-1",
                    validation_snapshot={},
                    created_at=day_start_utc + timedelta(minutes=1),
                    applied_at=day_start_utc + timedelta(minutes=2),
                    updated_at=day_start_utc + timedelta(minutes=2),
                ),
                PromoRedemption(
                    id=uuid4(),
                    promo_code_id=promo_code_id,
                    user_id=user_2,
                    status="REJECTED",
                    reject_reason="NOT_APPLICABLE",
                    reserved_until=None,
                    applied_purchase_id=None,
                    grant_entitlement_id=None,
                    idempotency_key="analytics-redemption-2",
                    validation_snapshot={},
                    created_at=day_start_utc + timedelta(minutes=3),
                    applied_at=None,
                    updated_at=day_start_utc + timedelta(minutes=3),
                ),
            ]
        )

        session.add_all(
            [
                QuizSession(
                    id=uuid4(),
                    user_id=user_1,
                    mode_code="ARTIKEL_SPRINT",
                    source="MENU",
                    status="COMPLETED",
                    energy_cost_total=1,
                    question_id="q1",
                    friend_challenge_id=None,
                    friend_challenge_round=None,
                    started_at=day_start_utc + timedelta(hours=4),
                    completed_at=day_start_utc + timedelta(hours=4, minutes=3),
                    local_date_berlin=local_day,
                    idempotency_key="analytics-session-1",
                ),
                QuizSession(
                    id=uuid4(),
                    user_id=user_2,
                    mode_code="ARTIKEL_SPRINT",
                    source="MENU",
                    status="STARTED",
                    energy_cost_total=1,
                    question_id="q2",
                    friend_challenge_id=None,
                    friend_challenge_round=None,
                    started_at=day_start_utc + timedelta(hours=5),
                    completed_at=None,
                    local_date_berlin=local_day,
                    idempotency_key="analytics-session-2",
                ),
            ]
        )

        session.add_all(
            [
                AnalyticsEvent(
                    event_type="gameplay_energy_zero",
                    source="SYSTEM",
                    user_id=user_1,
                    local_date_berlin=local_day,
                    payload={},
                    happened_at=day_start_utc + timedelta(hours=6),
                ),
                AnalyticsEvent(
                    event_type="streak_lost",
                    source="SYSTEM",
                    user_id=user_2,
                    local_date_berlin=local_day,
                    payload={},
                    happened_at=day_start_utc + timedelta(hours=6, minutes=30),
                ),
                AnalyticsEvent(
                    event_type="referral_reward_milestone_available",
                    source="WORKER",
                    user_id=None,
                    local_date_berlin=local_day,
                    payload={},
                    happened_at=day_start_utc + timedelta(hours=7),
                ),
                AnalyticsEvent(
                    event_type="purchase_init_created",
                    source="BOT",
                    user_id=user_1,
                    local_date_berlin=local_day,
                    payload={},
                    happened_at=day_start_utc + timedelta(hours=7, minutes=10),
                ),
                AnalyticsEvent(
                    event_type="purchase_invoice_sent",
                    source="BOT",
                    user_id=user_1,
                    local_date_berlin=local_day,
                    payload={},
                    happened_at=day_start_utc + timedelta(hours=7, minutes=11),
                ),
                AnalyticsEvent(
                    event_type="purchase_precheckout_ok",
                    source="BOT",
                    user_id=user_1,
                    local_date_berlin=local_day,
                    payload={},
                    happened_at=day_start_utc + timedelta(hours=7, minutes=12),
                ),
                AnalyticsEvent(
                    event_type="purchase_paid_uncredited",
                    source="BOT",
                    user_id=user_1,
                    local_date_berlin=local_day,
                    payload={},
                    happened_at=day_start_utc + timedelta(hours=7, minutes=13),
                ),
                AnalyticsEvent(
                    event_type="purchase_credited",
                    source="BOT",
                    user_id=user_1,
                    local_date_berlin=local_day,
                    payload={},
                    happened_at=day_start_utc + timedelta(hours=7, minutes=14),
                ),
                *[
                    AnalyticsEvent(
                        event_type=event_type,
                        source="BOT",
                        user_id=user_1,
                        local_date_berlin=local_day,
                        payload={},
                        happened_at=day_start_utc + timedelta(hours=8, minutes=offset),
                    )
                    for offset, (event_type, _field_name) in enumerate(DUEL_FUNNEL_EVENTS)
                ],
            ]
        )

    result = await run_analytics_daily_aggregation_async(days_back=1)
    assert result["days_processed"] == 1

    async with SessionLocal.begin() as session:
        row = await session.get(AnalyticsDaily, local_day)

    assert row is not None
    assert row.dau == 3
    assert row.wau == 3
    assert row.mau == 4
    assert row.purchases_credited_total == 3
    assert row.purchasers_total == 3
    assert float(row.purchase_rate) == pytest.approx(1.0)
    assert row.promo_redemptions_total == 2
    assert row.promo_redemptions_applied_total == 1
    assert float(row.promo_redemption_rate) == pytest.approx(0.5)
    assert row.promo_to_paid_conversions_total == 1
    assert row.quiz_sessions_started_total == 2
    assert row.quiz_sessions_completed_total == 1
    assert float(row.gameplay_completion_rate) == pytest.approx(0.5)
    assert row.energy_zero_events_total == 1
    assert row.streak_lost_events_total == 1
    assert row.referral_reward_milestone_events_total == 1
    assert row.referral_reward_granted_events_total == 0
    assert row.purchase_init_events_total == 1
    assert row.purchase_invoice_sent_events_total == 1
    assert row.purchase_precheckout_ok_events_total == 1
    assert row.purchase_paid_uncredited_events_total == 1
    assert row.purchase_credited_events_total == 1
    for _event_type, field_name in DUEL_FUNNEL_EVENTS:
        assert getattr(row, field_name) == 1
