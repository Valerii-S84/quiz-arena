from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.workers.tasks import payments_reliability_async


@pytest.mark.asyncio
async def test_telegram_stars_reconciliation_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        payments_reliability_async,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_stars_reconciliation_enabled=False,
            telegram_stars_reconciliation_dry_run=True,
            telegram_stars_auto_recovery_enabled=False,
        ),
    )

    result = await payments_reliability_async.run_telegram_stars_reconciliation_async()

    assert result == {
        "status": "disabled",
        "dry_run": True,
        "auto_recovery_enabled": False,
        "transactions_examined": 0,
    }


@pytest.mark.asyncio
async def test_telegram_stars_reconciliation_enabled_remains_dry_run(monkeypatch) -> None:
    monkeypatch.setattr(
        payments_reliability_async,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_stars_reconciliation_enabled=True,
            telegram_stars_reconciliation_dry_run=True,
            telegram_stars_auto_recovery_enabled=False,
        ),
    )

    result = await payments_reliability_async.run_telegram_stars_reconciliation_async()

    assert result == {
        "status": "dry_run_not_started",
        "dry_run": True,
        "auto_recovery_enabled": False,
        "transactions_examined": 0,
    }
