from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.routes.admin import users_helpers
from app.db.models.admin_audit_log import AdminAuditLog
from app.db.models.entitlements import Entitlement
from app.db.session import SessionLocal
from app.main import app
from tests.integration.admin_promo_test_support import (
    admin_headers,
    create_user,
    set_admin_authority,
)

NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def freeze_bonus_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(users_helpers, "datetime", FrozenDatetime)


async def _premium(user_id: int) -> Entitlement:
    async with SessionLocal() as session:
        return (
            await session.execute(
                select(Entitlement).where(
                    Entitlement.user_id == user_id,
                    Entitlement.entitlement_type == "PREMIUM",
                    Entitlement.status == "ACTIVE",
                )
            )
        ).scalar_one()


async def _grant(user_id: int, amount: int) -> None:
    async with SessionLocal.begin() as session:
        await users_helpers.apply_bonus(
            session, user_id=user_id, bonus_type="premium_days", amount=amount
        )


async def test_repeated_premium_bonus_api_persists_extension_and_audit() -> None:
    await set_admin_authority()
    user_id = await create_user("premium-bonus-api")
    started_at = datetime.now(timezone.utc)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        for amount in (7, 3):
            response = await client.post(
                f"/admin/users/{user_id}/bonus",
                json={"type": "premium_days", "amount": amount},
                headers=admin_headers(role="admin"),
            )
            assert response.status_code == 200
            assert response.json()["result"]["amount"] == amount
        profile = await client.get(f"/admin/users/{user_id}", headers=admin_headers(role="admin"))
    assert profile.status_code == 200
    bonuses = [
        row
        for row in profile.json()["timeline"]
        if row["type"] == "admin_bonus_premium_days"
        and datetime.fromisoformat(row["created_at"]) >= started_at
    ]
    assert sorted(row["payload"]["amount"] for row in bonuses) == [3, 7]
    entitlement = await _premium(user_id)
    assert entitlement.starts_at == NOW
    assert entitlement.ends_at == NOW + timedelta(days=10)
    async with SessionLocal() as session:
        audits = (
            await session.scalars(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "user_bonus",
                    AdminAuditLog.target_id == str(user_id),
                    AdminAuditLog.created_at >= started_at,
                )
            )
        ).all()
    assert sorted(cast(int, row.payload["amount"]) for row in audits) == [3, 7]


@pytest.mark.parametrize("remaining_days", [5, 0, -1, None])
async def test_premium_bonus_preserves_existing_entitlement(
    remaining_days: int | None,
) -> None:
    user_id = await create_user("premium-bonus-existing")
    ends_at = None if remaining_days is None else NOW + timedelta(days=remaining_days)
    async with SessionLocal.begin() as session:
        original = Entitlement(
            user_id=user_id,
            entitlement_type="PREMIUM",
            scope="PREMIUM_YEAR",
            status="ACTIVE",
            starts_at=NOW - timedelta(days=30),
            ends_at=ends_at,
            idempotency_key=f"test-premium:{uuid4()}",
            metadata_={"preserve": True},
            created_at=NOW - timedelta(days=30),
            updated_at=NOW - timedelta(days=30),
        )
        session.add(original)
        await session.flush()
        original_id = original.id
    await _grant(user_id, 3)
    entitlement = await _premium(user_id)
    expected_end = None if ends_at is None else max(ends_at, NOW) + timedelta(days=3)
    assert entitlement.id == original_id
    assert entitlement.ends_at == expected_end
    assert entitlement.scope == "PREMIUM_YEAR"
    assert entitlement.starts_at == NOW - timedelta(days=30)
    assert entitlement.metadata_ == {"preserve": True}


@pytest.mark.parametrize("existing", [False, True])
async def test_concurrent_premium_bonuses_keep_one_entitlement_and_all_days(existing: bool) -> None:
    user_id = await create_user("premium-bonus-concurrent")
    if existing:
        await _grant(user_id, 5)
    await asyncio.gather(_grant(user_id, 7), _grant(user_id, 3))
    entitlement = await _premium(user_id)
    assert entitlement.ends_at == NOW + timedelta(days=15 if existing else 10)
