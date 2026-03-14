from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.economy.referrals.service.rewards_grant as rewards_grant

UTC = timezone.utc


@pytest.mark.asyncio
async def test_grant_mega_pack_reward_credits_energy_and_creates_only_missing_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    credited: list[dict[str, object]] = []
    ledger_entries: list[object] = []
    mode_accesses: list[object] = []
    existing_key = f"referral:reward:mode:33:{rewards_grant.MEGA_PACK_MODE_CODES[0]}"

    async def _fake_credit_paid_energy(_session, **payload):
        credited.append(payload)

    async def _fake_create_ledger(_session, *, entry):
        ledger_entries.append(entry)

    async def _fake_get_by_idempotency_key(_session, *, idempotency_key: str):
        if idempotency_key == existing_key:
            return SimpleNamespace(id=1)
        return None

    async def _fake_get_latest_active_end(
        _session, *, user_id: int, mode_code: str, source: str, now_utc: datetime
    ):
        if mode_code == rewards_grant.MEGA_PACK_MODE_CODES[1]:
            return now_utc + timedelta(hours=3)
        return None

    async def _fake_create_mode_access(_session, *, mode_access):
        mode_accesses.append(mode_access)

    monkeypatch.setattr(rewards_grant.EnergyService, "credit_paid_energy", _fake_credit_paid_energy)
    monkeypatch.setattr(rewards_grant.LedgerRepo, "create", _fake_create_ledger)
    monkeypatch.setattr(
        rewards_grant.ModeAccessRepo,
        "get_by_idempotency_key",
        _fake_get_by_idempotency_key,
    )
    monkeypatch.setattr(
        rewards_grant.ModeAccessRepo,
        "get_latest_active_end",
        _fake_get_latest_active_end,
    )
    monkeypatch.setattr(rewards_grant.ModeAccessRepo, "create", _fake_create_mode_access)

    await rewards_grant._grant_mega_pack_reward(
        object(),
        user_id=5,
        referral_id=33,
        now_utc=now_utc,
    )

    assert credited == [
        {
            "user_id": 5,
            "amount": 15,
            "idempotency_key": "referral:reward:energy:33",
            "now_utc": now_utc,
            "source": "REFERRAL",
        }
    ]
    assert ledger_entries[0].idempotency_key == "referral:reward:mode_access:33"
    assert ledger_entries[0].metadata_ == {"reward_code": rewards_grant.REWARD_CODE_MEGA_PACK}
    assert len(mode_accesses) == 2
    assert {item.mode_code for item in mode_accesses} == set(rewards_grant.MEGA_PACK_MODE_CODES[1:])
    second_mode = next(
        item for item in mode_accesses if item.mode_code == rewards_grant.MEGA_PACK_MODE_CODES[1]
    )
    assert second_mode.starts_at == now_utc + timedelta(hours=3)
    assert second_mode.ends_at == now_utc + timedelta(hours=27)


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
async def test_grant_reward_dispatches_by_reward_code(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def _fake_premium(*_args, **_kwargs):
        calls.append("premium")

    async def _fake_mega(*_args, **_kwargs):
        calls.append("mega")

    monkeypatch.setattr(rewards_grant, "_grant_premium_starter_reward", _fake_premium)
    monkeypatch.setattr(rewards_grant, "_grant_mega_pack_reward", _fake_mega)

    await rewards_grant._grant_reward(
        object(),
        user_id=1,
        referral_id=1,
        reward_code=rewards_grant.REWARD_CODE_PREMIUM_STARTER,
        now_utc=datetime.now(UTC),
    )
    await rewards_grant._grant_reward(
        object(),
        user_id=1,
        referral_id=2,
        reward_code=rewards_grant.REWARD_CODE_MEGA_PACK,
        now_utc=datetime.now(UTC),
    )

    assert calls == ["premium", "mega"]
