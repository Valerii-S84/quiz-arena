from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import internal_offers
from app.db.models.offers_impressions import OfferImpression
from app.db.models.purchases import Purchase
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.offers.constants import OFFER_NOT_SHOW_DISMISS_REASON
from app.main import app

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=60_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"O{uuid4().hex[:10]}",
            username=None,
            first_name="OfferDashboard",
            referred_by_user_id=None,
        )
        return user.id


def _purchase(
    *,
    purchase_id: str,
    user_id: int,
    product_code: str,
    created_at: datetime,
) -> Purchase:
    return Purchase(
        id=uuid4(),
        user_id=user_id,
        product_code=product_code,
        product_type="MICRO",
        base_stars_amount=10,
        discount_stars_amount=0,
        stars_amount=10,
        currency="XTR",
        status="CREDITED",
        applied_promo_code_id=None,
        idempotency_key=f"offer-dashboard:{purchase_id}",
        invoice_payload=f"offer-dashboard:invoice:{purchase_id}",
        telegram_payment_charge_id=None,
        telegram_pre_checkout_query_id=None,
        raw_successful_payment=None,
        created_at=created_at,
        paid_at=created_at,
        credited_at=created_at,
        refunded_at=None,
    )


async def _seed_offer_dashboard_dataset(now_utc: datetime) -> None:
    user_1 = await _create_user("offer-dashboard-u1")
    user_2 = await _create_user("offer-dashboard-u2")
    user_3 = await _create_user("offer-dashboard-u3")

    purchase_1 = _purchase(
        purchase_id="p1",
        user_id=user_1,
        product_code="ENERGY_10",
        created_at=now_utc - timedelta(hours=2),
    )
    purchase_2 = _purchase(
        purchase_id="p2",
        user_id=user_3,
        product_code="MEGA_PACK_15",
        created_at=now_utc - timedelta(hours=1),
    )

    async with SessionLocal.begin() as session:
        session.add_all([purchase_1, purchase_2])
        await session.flush()
        session.add_all(
            [
                OfferImpression(
                    user_id=user_1,
                    offer_code="OFFER_ENERGY_ZERO",
                    trigger_code="TRG_ENERGY_ZERO",
                    priority=100,
                    shown_at=now_utc - timedelta(hours=2),
                    local_date_berlin=date(2026, 2, 19),
                    clicked_at=now_utc - timedelta(hours=2) + timedelta(minutes=2),
                    converted_purchase_id=purchase_1.id,
                    dismiss_reason=None,
                    idempotency_key=f"offer-dashboard:{uuid4().hex}",
                ),
                OfferImpression(
                    user_id=user_1,
                    offer_code="OFFER_ENERGY_ZERO",
                    trigger_code="TRG_ENERGY_ZERO",
                    priority=100,
                    shown_at=now_utc - timedelta(minutes=90),
                    local_date_berlin=date(2026, 2, 19),
                    clicked_at=now_utc - timedelta(minutes=89),
                    converted_purchase_id=None,
                    dismiss_reason=OFFER_NOT_SHOW_DISMISS_REASON,
                    idempotency_key=f"offer-dashboard:{uuid4().hex}",
                ),
                OfferImpression(
                    user_id=user_2,
                    offer_code="OFFER_LOCKED_MODE_MEGA",
                    trigger_code="TRG_LOCKED_MODE_CLICK",
                    priority=90,
                    shown_at=now_utc - timedelta(minutes=80),
                    local_date_berlin=date(2026, 2, 19),
                    clicked_at=None,
                    converted_purchase_id=None,
                    dismiss_reason=None,
                    idempotency_key=f"offer-dashboard:{uuid4().hex}",
                ),
                OfferImpression(
                    user_id=user_3,
                    offer_code="OFFER_LOCKED_MODE_MEGA",
                    trigger_code="TRG_LOCKED_MODE_CLICK",
                    priority=90,
                    shown_at=now_utc - timedelta(minutes=70),
                    local_date_berlin=date(2026, 2, 19),
                    clicked_at=now_utc - timedelta(minutes=69),
                    converted_purchase_id=purchase_2.id,
                    dismiss_reason=None,
                    idempotency_key=f"offer-dashboard:{uuid4().hex}",
                ),
                OfferImpression(
                    user_id=user_3,
                    offer_code="OFFER_COMEBACK_3D",
                    trigger_code="TRG_COMEBACK_3D",
                    priority=85,
                    shown_at=now_utc - timedelta(minutes=50),
                    local_date_berlin=date(2026, 2, 19),
                    clicked_at=None,
                    converted_purchase_id=None,
                    dismiss_reason=OFFER_NOT_SHOW_DISMISS_REASON,
                    idempotency_key=f"offer-dashboard:{uuid4().hex}",
                ),
                OfferImpression(
                    user_id=user_2,
                    offer_code="OFFER_COMEBACK_3D",
                    trigger_code="TRG_COMEBACK_3D",
                    priority=85,
                    shown_at=now_utc - timedelta(minutes=40),
                    local_date_berlin=date(2026, 2, 19),
                    clicked_at=None,
                    converted_purchase_id=None,
                    dismiss_reason=None,
                    idempotency_key=f"offer-dashboard:{uuid4().hex}",
                ),
            ]
        )


@pytest.mark.asyncio
async def test_internal_offers_dashboard_returns_funnel_metrics_and_alert_flags(monkeypatch) -> None:
    now_utc = datetime.now(UTC)
    await _seed_offer_dashboard_dataset(now_utc)

    monkeypatch.setattr(
        internal_offers,
        "get_settings",
        lambda: SimpleNamespace(
            internal_api_token="internal-secret",
            internal_api_allowlist="127.0.0.1/32",
            offers_alert_min_impressions=1,
            offers_alert_min_conversion_rate=0.40,
            offers_alert_max_dismiss_rate=0.30,
            offers_alert_max_impressions_per_user=1.5,
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/internal/offers/dashboard?window_hours=24",
            headers={"X-Internal-Token": "internal-secret"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["window_hours"] == 24
    assert payload["impressions_total"] == 6
    assert payload["unique_users"] == 3
    assert payload["clicks_total"] == 3
    assert payload["dismissals_total"] == 2
    assert payload["conversions_total"] == 2
    assert payload["click_through_rate"] == pytest.approx(0.5)
    assert payload["conversion_rate"] == pytest.approx(2 / 6)
    assert payload["dismiss_rate"] == pytest.approx(2 / 6)
    assert payload["impressions_per_user"] == pytest.approx(2.0)

    assert payload["top_offer_codes"] == {
        "OFFER_COMEBACK_3D": 2,
        "OFFER_ENERGY_ZERO": 2,
        "OFFER_LOCKED_MODE_MEGA": 2,
    }

    assert payload["thresholds"] == {
        "min_impressions": 1,
        "min_conversion_rate": 0.4,
        "max_dismiss_rate": 0.3,
        "max_impressions_per_user": 1.5,
    }
    assert payload["alerts"] == {
        "thresholds_applied": True,
        "conversion_drop_detected": True,
        "spam_anomaly_detected": True,
        "conversion_rate_below_threshold": True,
        "dismiss_rate_above_threshold": True,
        "impressions_per_user_above_threshold": True,
    }
