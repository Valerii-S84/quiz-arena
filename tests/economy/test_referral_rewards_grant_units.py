from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.economy.referrals.service.rewards_grant as rewards_grant

UTC = timezone.utc


@pytest.mark.asyncio
async def test_grant_premium_starter_reward_extends_active_entitlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    active_entitlement = SimpleNamespace(
        ends_at=now_utc + timedelta(days=5),
        updated_at=None,
    )
    created_entitlements: list[object] = []
    ledger_entries: list[object] = []

    async def _fake_get_active_premium_for_update(_session, user_id: int, now_utc: datetime):
        return active_entitlement

    async def _fake_create_entitlement(_session, *, entitlement):
        created_entitlements.append(entitlement)
        return entitlement

    async def _fake_create_ledger(_session, *, entry):
        ledger_entries.append(entry)

    monkeypatch.setattr(
        rewards_grant.EntitlementsRepo,
        "get_active_premium_for_update",
        _fake_get_active_premium_for_update,
    )
    monkeypatch.setattr(rewards_grant.EntitlementsRepo, "create", _fake_create_entitlement)
    monkeypatch.setattr(rewards_grant.LedgerRepo, "create", _fake_create_ledger)

    await rewards_grant._grant_premium_starter_reward(
        object(),
        user_id=9,
        referral_id=44,
        now_utc=now_utc,
    )

    assert active_entitlement.ends_at == now_utc + timedelta(days=12)
    assert active_entitlement.updated_at == now_utc
    assert created_entitlements == []
    assert ledger_entries[0].idempotency_key == "referral:reward:premium_ledger:44"


@pytest.mark.asyncio
async def test_grant_premium_starter_reward_creates_new_entitlement_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    created_entitlements: list[object] = []
    ledger_entries: list[object] = []

    async def _fake_get_active_premium_for_update(_session, user_id: int, now_utc: datetime):
        return None

    async def _fake_create_entitlement(_session, *, entitlement):
        created_entitlements.append(entitlement)
        return entitlement

    async def _fake_create_ledger(_session, *, entry):
        ledger_entries.append(entry)

    monkeypatch.setattr(
        rewards_grant.EntitlementsRepo,
        "get_active_premium_for_update",
        _fake_get_active_premium_for_update,
    )
    monkeypatch.setattr(rewards_grant.EntitlementsRepo, "create", _fake_create_entitlement)
    monkeypatch.setattr(rewards_grant.LedgerRepo, "create", _fake_create_ledger)

    await rewards_grant._grant_premium_starter_reward(
        object(),
        user_id=9,
        referral_id=45,
        now_utc=now_utc,
    )

    entitlement = created_entitlements[0]
    assert entitlement.user_id == 9
    assert entitlement.scope == "PREMIUM_STARTER"
    assert entitlement.idempotency_key == "referral:reward:premium:45"
    assert entitlement.ends_at == now_utc + timedelta(days=7)
    assert ledger_entries[0].metadata_ == {"reward_code": rewards_grant.REWARD_CODE_PREMIUM_STARTER}


@pytest.mark.asyncio
async def test_grant_reward_dispatches_premium_starter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _fake_premium(*_args, **_kwargs):
        calls.append("premium")

    monkeypatch.setattr(rewards_grant, "_grant_premium_starter_reward", _fake_premium)

    await rewards_grant._grant_reward(
        object(),
        user_id=1,
        referral_id=1,
        reward_code=rewards_grant.REWARD_CODE_PREMIUM_STARTER,
        now_utc=datetime.now(UTC),
    )

    assert calls == ["premium"]
