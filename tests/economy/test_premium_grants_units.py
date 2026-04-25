from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

import app.economy.premium_grants as premium_grants
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_grant_premium_days_extends_active_entitlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    active_entitlement = SimpleNamespace(
        ends_at=now_utc + timedelta(days=5),
        updated_at=None,
    )
    ledger_entries: list[Any] = []

    async def _fake_get_active_premium_for_update(_session, user_id: int, now_utc: datetime):
        return active_entitlement

    async def _fake_create_ledger(_session, *, entry):
        ledger_entries.append(entry)

    monkeypatch.setattr(
        premium_grants.EntitlementsRepo,
        "get_active_premium_for_update",
        _fake_get_active_premium_for_update,
    )
    monkeypatch.setattr(premium_grants.LedgerRepo, "create", _fake_create_ledger)

    entitlement = await premium_grants.grant_premium_days(
        _Session(),
        user_id=9,
        grant_days=3,
        scope="PREMIUM_3_DAYS",
        now_utc=now_utc,
        source="TOURNAMENT",
        entry_type="TOURNAMENT_REWARD",
        entitlement_idempotency_key="entitlement:1",
        ledger_idempotency_key="ledger:1",
        metadata={"rank": 1},
    )

    assert entitlement is active_entitlement
    assert active_entitlement.ends_at == now_utc + timedelta(days=8)
    assert active_entitlement.updated_at == now_utc
    assert ledger_entries[0].idempotency_key == "ledger:1"


@pytest.mark.asyncio
async def test_grant_premium_days_creates_new_entitlement_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    created_entitlements: list[Any] = []
    ledger_entries: list[Any] = []

    async def _fake_get_active_premium_for_update(_session, user_id: int, now_utc: datetime):
        return None

    async def _fake_create_entitlement(_session, *, entitlement):
        created_entitlements.append(entitlement)
        return entitlement

    async def _fake_create_ledger(_session, *, entry):
        ledger_entries.append(entry)

    monkeypatch.setattr(
        premium_grants.EntitlementsRepo,
        "get_active_premium_for_update",
        _fake_get_active_premium_for_update,
    )
    monkeypatch.setattr(premium_grants.EntitlementsRepo, "create", _fake_create_entitlement)
    monkeypatch.setattr(premium_grants.LedgerRepo, "create", _fake_create_ledger)

    entitlement = await premium_grants.grant_premium_days(
        _Session(),
        user_id=9,
        grant_days=3,
        scope="PREMIUM_3_DAYS",
        now_utc=now_utc,
        source="TOURNAMENT",
        entry_type="TOURNAMENT_REWARD",
        entitlement_idempotency_key="entitlement:2",
        ledger_idempotency_key="ledger:2",
        metadata={"rank": 1, "reward_type": "PREMIUM_3_DAYS"},
    )

    assert entitlement is created_entitlements[0]
    assert entitlement.scope == "PREMIUM_3_DAYS"
    assert entitlement.ends_at == now_utc + timedelta(days=3)
    assert entitlement.idempotency_key == "entitlement:2"
    assert ledger_entries[0].metadata_ == {"rank": 1, "reward_type": "PREMIUM_3_DAYS"}
