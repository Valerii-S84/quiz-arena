from __future__ import annotations

import pytest

from app.db.models.ledger_entries import LedgerEntry
from app.economy.purchases.catalog import ProductSpec
from app.economy.purchases.service import credit_assets as purchase_credit_assets
from tests.purchase_service_test_helpers import NOW, SessionStub, promo_code, purchase_model
from tests.type_helpers import build_promo_redemption


@pytest.mark.asyncio
async def test_credit_purchase_assets_applies_energy_streak_promo_and_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = purchase_model(stars_amount=5, applied_promo_code_id=21, status="PAID_UNCREDITED")
    product = ProductSpec("ENERGY_10", "MICRO", "Energy", "Energy", 5, 10, grants_streak_saver=True)
    redemption = build_promo_redemption(status="RESERVED", applied_purchase_id=purchase.id)
    code = promo_code(id=21, used_total=3)
    energy_calls: list[dict[str, object]] = []
    streak_calls: list[dict[str, object]] = []
    ledger_entries: list[LedgerEntry] = []
    events: list[str] = []

    async def _fake_credit_paid_energy(_session, **kwargs) -> None:
        energy_calls.append(kwargs)

    async def _fake_add_streak_saver_token(_session, *, user_id: int, now_utc) -> None:
        streak_calls.append({"user_id": user_id, "now_utc": now_utc})

    async def _fake_validate_reserved_discount(*_args, **_kwargs):
        return redemption, code

    async def _fake_create(_session, *, entry: LedgerEntry):
        ledger_entries.append(entry)
        return entry

    async def _fake_get_purchase_credit_for_update(_session, *, purchase_id):
        assert purchase_id == purchase.id
        return None

    async def _fake_emit_purchase_event(
        _session, *, event_type: str, purchase, happened_at, extra_payload=None
    ) -> None:
        assert purchase.id == purchase.id
        assert happened_at == NOW
        assert extra_payload is None
        events.append(event_type)

    monkeypatch.setattr(
        purchase_credit_assets.EnergyService, "credit_paid_energy", _fake_credit_paid_energy
    )
    monkeypatch.setattr(
        purchase_credit_assets.StreakRepo, "add_streak_saver_token", _fake_add_streak_saver_token
    )
    monkeypatch.setattr(
        purchase_credit_assets,
        "_validate_reserved_discount_for_purchase",
        _fake_validate_reserved_discount,
    )
    monkeypatch.setattr(
        purchase_credit_assets.LedgerRepo,
        "get_purchase_credit_for_update",
        _fake_get_purchase_credit_for_update,
    )
    monkeypatch.setattr(purchase_credit_assets.LedgerRepo, "create", _fake_create)
    monkeypatch.setattr(purchase_credit_assets, "_emit_purchase_event", _fake_emit_purchase_event)

    await purchase_credit_assets.credit_purchase_assets(
        SessionStub(),
        user_id=7,
        purchase=purchase,
        product=product,
        now_utc=NOW,
    )

    assert energy_calls == [
        {
            "user_id": 7,
            "amount": 10,
            "idempotency_key": f"credit:energy:{purchase.id}",
            "now_utc": NOW,
            "write_ledger_entry": False,
        }
    ]
    assert streak_calls == [{"user_id": 7, "now_utc": NOW}]
    assert redemption.status == "APPLIED"
    assert redemption.applied_at == NOW
    assert code.used_total == 4
    assert ledger_entries[0].metadata_["asset_breakdown"] == {
        "paid_energy": 10,
        "streak_saver_tokens": 1,
    }
    assert purchase.status == "CREDITED"
    assert purchase.credited_at == NOW
    assert events == ["purchase_credited"]


@pytest.mark.asyncio
async def test_credit_purchase_assets_applies_premium_without_purchase_ledger_for_zero_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = purchase_model(
        product_code="PREMIUM_WEEK",
        product_type="PREMIUM",
        stars_amount=0,
        status="PAID_UNCREDITED",
    )
    product = ProductSpec("PREMIUM_WEEK", "PREMIUM", "Premium", "Premium", 29, 0, premium_days=7)
    premium_calls: list[dict[str, object]] = []
    events: list[str] = []

    async def _fake_apply_premium_entitlement(_session, **kwargs) -> None:
        premium_calls.append(kwargs)

    async def _fail_create(_session, *, entry: LedgerEntry):
        pytest.fail("purchase ledger entry should not be created for zero stars purchase")

    async def _fake_emit_purchase_event(
        _session, *, event_type: str, purchase, happened_at, extra_payload=None
    ) -> None:
        assert happened_at == NOW
        assert extra_payload is None
        events.append(event_type)

    monkeypatch.setattr(
        purchase_credit_assets, "_apply_premium_entitlement", _fake_apply_premium_entitlement
    )
    monkeypatch.setattr(purchase_credit_assets.LedgerRepo, "create", _fail_create)
    monkeypatch.setattr(purchase_credit_assets, "_emit_purchase_event", _fake_emit_purchase_event)

    await purchase_credit_assets.credit_purchase_assets(
        SessionStub(),
        user_id=7,
        purchase=purchase,
        product=product,
        now_utc=NOW,
    )

    assert premium_calls == [
        {
            "user_id": 7,
            "purchase": purchase,
            "product": product,
            "now_utc": NOW,
        }
    ]
    assert purchase.status == "CREDITED"
    assert purchase.credited_at == NOW
    assert events == ["purchase_credited"]


@pytest.mark.asyncio
async def test_credit_purchase_assets_keeps_already_applied_promo_usage_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = purchase_model(stars_amount=0, applied_promo_code_id=21, status="PAID_UNCREDITED")
    product = ProductSpec("PROMO", "MICRO", "Promo", "Promo", 0, 0)
    redemption = build_promo_redemption(status="APPLIED", applied_purchase_id=purchase.id)
    code = promo_code(id=21, used_total=5)
    events: list[str] = []

    async def _fake_validate_reserved_discount(*_args, **_kwargs):
        return redemption, code

    async def _fake_emit_purchase_event(
        _session, *, event_type: str, purchase, happened_at, extra_payload=None
    ) -> None:
        assert happened_at == NOW
        events.append(event_type)

    monkeypatch.setattr(
        purchase_credit_assets,
        "_validate_reserved_discount_for_purchase",
        _fake_validate_reserved_discount,
    )
    monkeypatch.setattr(purchase_credit_assets, "_emit_purchase_event", _fake_emit_purchase_event)

    await purchase_credit_assets.credit_purchase_assets(
        SessionStub(),
        user_id=7,
        purchase=purchase,
        product=product,
        now_utc=NOW,
    )

    assert redemption.applied_at is None
    assert code.used_total == 5
    assert purchase.status == "CREDITED"
    assert events == ["purchase_credited"]


@pytest.mark.asyncio
async def test_credit_purchase_assets_skips_existing_purchase_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = purchase_model(stars_amount=5, status="PAID_UNCREDITED")
    product = ProductSpec("ENERGY_10", "MICRO", "Energy", "Energy", 5, 0)
    existing_ledger = object()
    events: list[str] = []

    async def _fake_get_purchase_credit_for_update(_session, *, purchase_id):
        assert purchase_id == purchase.id
        return existing_ledger

    async def _fail_create(_session, *, entry: LedgerEntry):
        del entry
        pytest.fail("existing purchase credit ledger should not be duplicated")

    async def _fake_emit_purchase_event(
        _session, *, event_type: str, purchase, happened_at, extra_payload=None
    ) -> None:
        assert happened_at == NOW
        assert extra_payload is None
        events.append(event_type)

    monkeypatch.setattr(
        purchase_credit_assets.LedgerRepo,
        "get_purchase_credit_for_update",
        _fake_get_purchase_credit_for_update,
    )
    monkeypatch.setattr(purchase_credit_assets.LedgerRepo, "create", _fail_create)
    monkeypatch.setattr(purchase_credit_assets, "_emit_purchase_event", _fake_emit_purchase_event)

    await purchase_credit_assets.credit_purchase_assets(
        SessionStub(),
        user_id=7,
        purchase=purchase,
        product=product,
        now_utc=NOW,
    )

    assert purchase.status == "CREDITED"
    assert purchase.credited_at == NOW
    assert events == ["purchase_credited"]
