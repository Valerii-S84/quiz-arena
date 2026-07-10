from __future__ import annotations

from argparse import Namespace

import pytest

from app.services.production_invariants import InvariantResult
from scripts import production_critical_invariants


@pytest.mark.asyncio
async def test_production_critical_invariants_json_output(monkeypatch, capsys) -> None:
    async def _checks(_now_utc):
        return [
            InvariantResult(
                name="paid_without_entitlement",
                status="FAIL",
                severity="P1",
                count=1,
                description="missing entitlement",
                correlation_key="paid_without_entitlement",
                safe_context={"check_name": "paid_without_entitlement", "count": 1},
            )
        ]

    monkeypatch.setattr(production_critical_invariants, "run_database_checks", _checks)

    exit_code = await production_critical_invariants._run(Namespace(json=True))

    captured = capsys.readouterr().out
    assert exit_code == 1
    assert '"name": "paid_without_entitlement"' in captured
    assert "telegram_bot_token" not in captured


@pytest.mark.asyncio
async def test_production_critical_invariants_text_output_clean(monkeypatch, capsys) -> None:
    async def _checks(_now_utc):
        return [
            InvariantResult(
                name="analytics_daily_stale",
                status="OK",
                severity="P2",
                count=0,
                description="fresh",
                correlation_key="analytics_daily_stale",
                safe_context={"check_name": "analytics_daily_stale", "count": 0},
            )
        ]

    monkeypatch.setattr(production_critical_invariants, "run_database_checks", _checks)

    exit_code = await production_critical_invariants._run(Namespace(json=False))

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "production_critical_invariants" in captured
    assert "analytics_daily_stale" in captured
