from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

import app.economy.offers.triggers as offer_triggers

UTC = timezone.utc


@pytest.mark.asyncio
async def test_build_trigger_codes_returns_energy_and_purchase_triggers_for_non_premium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 3, 13, 10, 0, tzinfo=UTC)

    async def _fake_get_energy_state(_session, _user_id):
        return SimpleNamespace(free_energy=1, paid_energy=1)

    async def _fake_get_streak_state(_session, _user_id):
        return SimpleNamespace(
            current_streak=0,
            today_status="PLAYED",
            last_activity_local_date=date(2026, 3, 13),
        )

    async def _fake_has_active_premium(_session, _user_id, _now_utc):
        return False

    async def _fake_count_paid_product_since(_session, *, product_code: str, **_kwargs):
        if product_code == "ENERGY_10":
            return 2
        return 0

    async def _false(*_args, **_kwargs):
        return False

    monkeypatch.setattr(offer_triggers.EnergyRepo, "get_by_user_id", _fake_get_energy_state)
    monkeypatch.setattr(offer_triggers.StreakRepo, "get_by_user_id", _fake_get_streak_state)
    monkeypatch.setattr(
        offer_triggers.EntitlementsRepo,
        "has_active_premium",
        _fake_has_active_premium,
    )
    monkeypatch.setattr(
        offer_triggers.PurchasesRepo,
        "count_paid_product_since",
        _fake_count_paid_product_since,
    )
    monkeypatch.setattr(
        offer_triggers.EntitlementsRepo,
        "has_recently_ended_premium_scope",
        _false,
    )
    monkeypatch.setattr(
        offer_triggers.EntitlementsRepo,
        "has_active_premium_scope_ending_within",
        _false,
    )
    monkeypatch.setattr(offer_triggers, "is_weekend_flash_window", lambda _local_now: False)
    monkeypatch.setattr(offer_triggers, "berlin_now", lambda _now_utc: _now_utc)

    result = await offer_triggers.build_trigger_codes(
        object(),
        user_id=5,
        now_utc=now_utc,
        trigger_event="ignored",
    )

    assert result == {
        offer_triggers.TRG_ENERGY_LOW,
        offer_triggers.TRG_ENERGY10_SECOND_BUY,
    }


@pytest.mark.asyncio
async def test_build_trigger_codes_returns_streak_and_comeback_triggers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 3, 14, 22, 30, tzinfo=UTC)

    async def _fake_get_energy_state(_session, _user_id):
        return SimpleNamespace(free_energy=5, paid_energy=0)

    async def _fake_get_streak_state(_session, _user_id):
        return SimpleNamespace(
            current_streak=30,
            today_status="NO_ACTIVITY",
            last_activity_local_date=date(2026, 3, 10),
        )

    async def _fake_has_active_premium(_session, _user_id, _now_utc):
        return False

    async def _fake_count_paid_product_since(_session, **_kwargs):
        return 0

    async def _fake_has_recently_ended_premium_scope(_session, **_kwargs):
        return True

    async def _fake_has_active_premium_scope_ending_within(_session, **_kwargs):
        return False

    monkeypatch.setattr(offer_triggers.EnergyRepo, "get_by_user_id", _fake_get_energy_state)
    monkeypatch.setattr(offer_triggers.StreakRepo, "get_by_user_id", _fake_get_streak_state)
    monkeypatch.setattr(
        offer_triggers.EntitlementsRepo,
        "has_active_premium",
        _fake_has_active_premium,
    )
    monkeypatch.setattr(
        offer_triggers.PurchasesRepo,
        "count_paid_product_since",
        _fake_count_paid_product_since,
    )
    monkeypatch.setattr(
        offer_triggers.EntitlementsRepo,
        "has_recently_ended_premium_scope",
        _fake_has_recently_ended_premium_scope,
    )
    monkeypatch.setattr(
        offer_triggers.EntitlementsRepo,
        "has_active_premium_scope_ending_within",
        _fake_has_active_premium_scope_ending_within,
    )
    monkeypatch.setattr(offer_triggers, "is_weekend_flash_window", lambda _local_now: True)
    monkeypatch.setattr(offer_triggers, "berlin_now", lambda _now_utc: _now_utc)

    result = await offer_triggers.build_trigger_codes(
        object(),
        user_id=5,
        now_utc=now_utc,
        trigger_event=None,
    )

    assert result == {
        offer_triggers.TRG_STREAK_GT7,
        offer_triggers.TRG_STREAK_RISK_22,
        offer_triggers.TRG_STREAK_MILESTONE_30,
        offer_triggers.TRG_COMEBACK_3D,
        offer_triggers.TRG_STARTER_EXPIRED,
        offer_triggers.TRG_WEEKEND_FLASH,
    }


@pytest.mark.asyncio
async def test_build_trigger_codes_keeps_month_expiring_for_premium_user_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 3, 15, 9, 0, tzinfo=UTC)

    async def _fake_get_energy_state(_session, _user_id):
        return SimpleNamespace(free_energy=0, paid_energy=0)

    async def _fake_get_streak_state(_session, _user_id):
        return None

    async def _fake_has_active_premium(_session, _user_id, _now_utc):
        return True

    async def _fake_count_paid_product_since(_session, **_kwargs):
        return 5

    async def _false(*_args, **_kwargs):
        return False

    async def _true(*_args, **_kwargs):
        return True

    monkeypatch.setattr(offer_triggers.EnergyRepo, "get_by_user_id", _fake_get_energy_state)
    monkeypatch.setattr(offer_triggers.StreakRepo, "get_by_user_id", _fake_get_streak_state)
    monkeypatch.setattr(
        offer_triggers.EntitlementsRepo,
        "has_active_premium",
        _fake_has_active_premium,
    )
    monkeypatch.setattr(
        offer_triggers.PurchasesRepo,
        "count_paid_product_since",
        _fake_count_paid_product_since,
    )
    monkeypatch.setattr(
        offer_triggers.EntitlementsRepo,
        "has_recently_ended_premium_scope",
        _false,
    )
    monkeypatch.setattr(
        offer_triggers.EntitlementsRepo,
        "has_active_premium_scope_ending_within",
        _true,
    )
    monkeypatch.setattr(offer_triggers, "is_weekend_flash_window", lambda _local_now: False)
    monkeypatch.setattr(offer_triggers, "berlin_now", lambda _now_utc: _now_utc)

    result = await offer_triggers.build_trigger_codes(
        object(),
        user_id=5,
        now_utc=now_utc,
        trigger_event="ignored",
    )

    assert result == {offer_triggers.TRG_MONTH_EXPIRING}
