from __future__ import annotations

import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from app.services.production_invariants import InvariantResult
from scripts import production_critical_invariants


def test_script_bootstraps_repo_root(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(Path(production_critical_invariants.__file__).resolve()), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "TELEGRAM_BOT_TOKEN": "123456:test-token",
            "TELEGRAM_WEBHOOK_SECRET": "test-webhook-secret",
        },
    )

    assert result.returncode == 0
    assert "Run read-only production critical invariants" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr


async def test_json_output_returns_blocking_exit_code(monkeypatch, capsys) -> None:
    async def _checks(_now_utc):
        return [_result(status="FAIL", severity="P1", count=1)]

    monkeypatch.setattr(production_critical_invariants, "run_database_checks", _checks)

    assert await production_critical_invariants._run(Namespace(json=True)) == 1
    output = capsys.readouterr().out
    assert '"name": "paid_without_entitlement"' in output
    assert "telegram_bot_token" not in output


async def test_text_output_keeps_p2_non_blocking(monkeypatch, capsys) -> None:
    async def _checks(_now_utc):
        return [_result(status="FAIL", severity="P2", count=1)]

    monkeypatch.setattr(production_critical_invariants, "run_database_checks", _checks)

    assert await production_critical_invariants._run(Namespace(json=False)) == 0
    assert "production_critical_invariants" in capsys.readouterr().out


def _result(*, status: str, severity: str, count: int) -> InvariantResult:
    return InvariantResult(
        name="paid_without_entitlement",
        status=status,
        severity=severity,
        count=count,
        description="missing entitlement",
        correlation_key="paid_without_entitlement",
        safe_context={"check_name": "paid_without_entitlement", "count": count},
    )
