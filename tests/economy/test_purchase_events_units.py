from __future__ import annotations

import pytest

from app.core.analytics_events import EVENT_SOURCE_SYSTEM
from app.economy.purchases.service import events as purchase_events
from tests.purchase_service_test_helpers import NOW, SessionStub, purchase_model


@pytest.mark.parametrize("extra_payload", [None, {"zero_cost": True}])
@pytest.mark.asyncio
async def test_emit_purchase_event_forwards_expected_payload(
    monkeypatch: pytest.MonkeyPatch,
    extra_payload: dict[str, object] | None,
) -> None:
    purchase = purchase_model(
        stars_amount=3,
        discount_stars_amount=2,
        applied_promo_code_id=21,
        status="PRECHECKOUT_OK",
    )
    calls: list[dict[str, object]] = []

    async def _fake_emit_analytics_event(
        _session,
        *,
        event_type: str,
        source: str,
        user_id: int | None,
        payload: dict[str, object] | None,
        happened_at,
    ) -> None:
        calls.append(
            {
                "event_type": event_type,
                "source": source,
                "user_id": user_id,
                "payload": payload,
                "happened_at": happened_at,
            }
        )

    monkeypatch.setattr(purchase_events, "emit_analytics_event", _fake_emit_analytics_event)

    await purchase_events._emit_purchase_event(
        SessionStub(),
        event_type="purchase_tested",
        purchase=purchase,
        happened_at=NOW,
        extra_payload=extra_payload,
    )

    expected_payload = {
        "purchase_id": str(purchase.id),
        "product_code": purchase.product_code,
        "product_type": purchase.product_type,
        "status": purchase.status,
        "stars_amount": purchase.stars_amount,
        "discount_stars_amount": purchase.discount_stars_amount,
    }
    if extra_payload is not None:
        expected_payload.update(extra_payload)

    assert calls == [
        {
            "event_type": "purchase_tested",
            "source": EVENT_SOURCE_SYSTEM,
            "user_id": purchase.user_id,
            "payload": expected_payload,
            "happened_at": NOW,
        }
    ]
